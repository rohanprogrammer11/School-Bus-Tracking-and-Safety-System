from flask import render_template, session, redirect, request, flash
from app.utils.notification_service import create_notification
from datetime import datetime
from app.driver.blueprint import driver_bp
from app.extensions import get_cursor


def format_time(t):
    if not t:
        return None

    if hasattr(t, "seconds"):
        hours = t.seconds // 3600
        minutes = (t.seconds % 3600) // 60
    else:
        h, m, *_ = str(t).split(":")
        hours = int(h)
        minutes = int(m)

    suffix = "AM" if hours < 12 else "PM"
    hours = hours % 12 or 12
    return f"{hours:02d}:{minutes:02d} {suffix}"


# ==========================
# DRIVER DASHBOARD
# ==========================
@driver_bp.route("/dashboard")
def driver_dashboard():

    if "user_id" not in session or session.get("role") != "driver":
        return redirect("/driver/login")

    driver_id = session["user_id"]
    org_id = session.get("org_id")

    db, cursor = get_cursor()

    try:
        # ================= DRIVER INFO =================
        cursor.execute("""
            SELECT name, phone, email
            FROM users
            WHERE id=%s AND role='driver'
        """, (driver_id,))
        driver = cursor.fetchone()

        # ================= TODAY ASSIGNMENTS =================
        cursor.execute("""
            SELECT
                da.id            AS assignment_id,
                da.assignment    AS assignment_type,
                da.assignment_time,
                da.assignment_date,
                b.id             AS bus_id,
                b.bus_number,
                r.route_name,
                bt.status        AS trip_status
            FROM driver_assignment da
            JOIN buses b ON b.id = da.bus_id
            JOIN routes r ON r.id = da.route_id
            LEFT JOIN bus_trip bt
               ON bt.id = (
                   SELECT id
                   FROM bus_trip
                   WHERE assignment_id = da.id
                     AND trip_date = CURDATE()
                   ORDER BY start_time DESC
                   LIMIT 1
               )
            WHERE da.driver_id=%s
              AND da.org_id=%s
              AND da.assignment_date = CURDATE()
            ORDER BY da.assignment_time
        """, (driver_id, org_id))

        rows = cursor.fetchall()

        pickup = None
        drop = None
        pickup_time = None
        drop_time = None
        bus_id = None
        bus_number = None
        route_name = None
        trip_date = None

        for r in rows:
            if r["assignment_type"] == "PICKUP":
                pickup = r
                pickup_time = format_time(r["assignment_time"])
                pickup_status = r["trip_status"]

            elif r["assignment_type"] == "DROP":
                drop = r
                drop_time = format_time(r["assignment_time"])
                drop_status = r["trip_status"]

            bus_id = r["bus_id"]
            bus_number = r["bus_number"]
            route_name = r["route_name"]
            trip_date = r["assignment_date"]

        # ================= STUDENTS =================
        students = []
        if route_name:
            cursor.execute("""
                SELECT
                    s.id,
                    s.name,
                    s.roll_no,
                    s.class_id,
                    rs.stop_name
                FROM student s
                JOIN route_stop rs ON rs.id = s.assigned_stop_id
                JOIN routes r ON r.id = rs.route_id
                WHERE r.route_name=%s
                  AND s.org_id=%s
                ORDER BY rs.stop_order
            """, (route_name, org_id))
            students = cursor.fetchall()

        return render_template(
            "driver/driver_dashboard.html",
            driver=driver,
            bus_id=bus_id,
            bus_number=bus_number,
            route_name=route_name,
            trip_date=trip_date,
            pickup=pickup,
            drop=drop,
            pickup_time=pickup_time,
            drop_time=drop_time,
            pickup_status=pickup_status if pickup else None,
            drop_status=drop_status if drop else None,
            students=students
        )

    finally:
        cursor.close()
        db.close()
        
# ==========================
# TRIP MAP
# ==========================
@driver_bp.route("/trip-map/<int:assignment_id>")
def trip_map(assignment_id):

    if "user_id" not in session or session.get("role") != "driver":
        return redirect("/driver/login")

    org_id = session.get("org_id")
    db, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT route_id, bus_id
            FROM driver_assignment
            WHERE id=%s AND org_id=%s
        """, (assignment_id, org_id))

        row = cursor.fetchone()
        if not row:
            return "Invalid assignment", 404

        route_id = row["route_id"]
        bus_id = row["bus_id"]

        cursor.execute("""
            SELECT stop_name, latitude, longitude, stop_order
            FROM route_stop
            WHERE route_id=%s
            ORDER BY stop_order ASC
        """, (route_id,))
        stops = cursor.fetchall()

    finally:
        cursor.close()
        db.close()

    return render_template(
        "driver/driver_trip_map.html",
        assignment_id=assignment_id,
        stops=stops,
        bus_id=bus_id
    )


# ==========================
# START TRIP
# ==========================
@driver_bp.route("/start-trip", methods=["POST"])
def start_trip():

    if "user_id" not in session or session.get("role") != "driver":
        return redirect("/driver/login")

    assignment_id = request.form.get("assignment_id")
    org_id = session.get("org_id")

    db, cursor = get_cursor()

    try:
        # =========================
        # Validate assignment date
        # =========================
        cursor.execute("""
            SELECT assignment_date, bus_id, route_id
            FROM driver_assignment
            WHERE id=%s AND org_id=%s
        """, (assignment_id, org_id))

        row = cursor.fetchone()
        if not row or row["assignment_date"] != datetime.today().date():
            flash("Trip can only be started today.", "danger")
            return redirect("/driver/dashboard")

        bus_id = row["bus_id"]
        route_id = row["route_id"]

        # =========================
        # Check if trip already started
        # =========================
        cursor.execute("""
            SELECT id
            FROM bus_trip
            WHERE assignment_id=%s
              AND trip_date=CURDATE()
              AND status='STARTED'
        """, (assignment_id,))
        existing = cursor.fetchone()

        # =========================
        # Insert trip (ONLY if not started)
        # =========================
        if not existing:
            cursor.execute("""
                INSERT INTO bus_trip (
                    assignment_id,
                    trip_date,
                    start_time,
                    status,
                    bus_id,
                    route_id,
                    distance_km
                )
                VALUES (
                    %s,
                    CURDATE(),
                    NOW(),
                    'STARTED',
                    %s,
                    %s,
                    0
                )
            """, (assignment_id, bus_id, route_id))

            db.commit()

    finally:
        cursor.close()
        db.close()

    return redirect(f"/driver/trip-map/{assignment_id}")


# ==========================
# END TRIP
# ==========================
@driver_bp.route("/end-trip", methods=["POST"])
def end_trip():

    if "user_id" not in session or session.get("role") != "driver":
        return redirect("/driver/login")

    assignment_id = request.form.get("assignment_id")
    org_id = session.get("org_id")

    db, cursor = get_cursor()

    try:
        # =========================
        # End the active trip
        # =========================
        cursor.execute("""
            UPDATE bus_trip
            SET end_time=NOW(), status='COMPLETED'
            WHERE assignment_id=%s
              AND trip_date=CURDATE()
              AND status='STARTED'
            ORDER BY start_time DESC
            LIMIT 1
        """, (assignment_id,))
        db.commit()

        # =========================
        # Get completed trip details
        # =========================
        cursor.execute("""
            SELECT
                bt.id AS trip_id,
                bt.distance_km,
                bt.bus_id,
                bt.route_id,
                b.mileage_kmpl
            FROM bus_trip bt
            JOIN buses b ON b.id = bt.bus_id
            WHERE bt.assignment_id=%s
              AND bt.trip_date=CURDATE()
              AND bt.status='COMPLETED'
            ORDER BY bt.end_time DESC
            LIMIT 1
        """, (assignment_id,))
        trip = cursor.fetchone()

        if trip:
            # =========================
            # Calculate distance (route based)
            # =========================
            cursor.execute("""
                SELECT round_trip_km
                FROM routes
                WHERE id=%s
            """, (trip["route_id"],))
            route = cursor.fetchone()

            distance_km = route["round_trip_km"] if route else 0

            cursor.execute("""
                UPDATE bus_trip
                SET distance_km=%s
                WHERE id=%s
            """, (distance_km, trip["trip_id"]))

            # =========================
            # Fuel calculation
            # =========================
            fuel_used = 0
            fuel_cost = 0
            fuel = None

            if trip["mileage_kmpl"] and trip["mileage_kmpl"] > 0:
                fuel_used = distance_km / trip["mileage_kmpl"]

                cursor.execute("""
                    SELECT price_per_unit
                    FROM fuel_price
                    WHERE org_id=%s
                    ORDER BY effective_from DESC
                    LIMIT 1
                """, (org_id,))
                fuel = cursor.fetchone()

                if fuel:
                    fuel_cost = fuel_used * fuel["price_per_unit"]

            # =========================
            # Insert fuel consumption
            # =========================
            cursor.execute("""
                INSERT INTO fuel_consumption (
                    org_id,
                    bus_id,
                    trip_id,
                    trip_date,
                    distance_km,
                    mileage_kmpl,
                    fuel_used,
                    fuel_price,
                    fuel_cost
                )
                VALUES (%s,%s,%s,CURDATE(),%s,%s,%s,%s,%s)
            """, (
                org_id,
                trip["bus_id"],
                trip["trip_id"],
                distance_km,
                trip["mileage_kmpl"],
                fuel_used,
                fuel["price_per_unit"] if fuel else 0,
                fuel_cost
            ))

            db.commit()

        flash("Trip ended successfully", "success")

    finally:
        cursor.close()
        db.close()

    return redirect("/driver/dashboard")


# ==========================
# LIVE LOCATION UPDATE
# ==========================
@driver_bp.route("/location-update", methods=["POST"])
def location_update():

    if "user_id" not in session or session.get("role") != "driver":
        return {"error": "unauthorized"}, 401

    data = request.get_json() or {}

    bus_id = data.get("bus_id")
    lat = data.get("latitude")
    lng = data.get("longitude")
    speed = data.get("speed", 0)

    if not bus_id or lat is None or lng is None:
        return {"error": "invalid location data"}, 400

    org_id = session.get("org_id")

    db, cursor = get_cursor()
    try:
        cursor.execute("""
            INSERT INTO location_update
            (org_id, bus_id, latitude, longitude, speed, event_time)
            VALUES (%s,%s,%s,%s,%s,NOW())
        """, (org_id, bus_id, lat, lng, speed))
        db.commit()
    finally:
        cursor.close()
        db.close()

    return {"status": "ok"}


# ==========================
# DRIVER SOS ALERT
# ==========================
@driver_bp.route("/send-sos", methods=["POST"])
def send_sos():

    if "user_id" not in session or session.get("role") != "driver":
        return {"status": "Unauthorized"}, 401

    driver_id = session["user_id"]
    org_id = session.get("org_id")

    data = request.get_json() or {}
    bus_id = data.get("bus_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")
    description = data.get("description", "Emergency SOS alert")

    if not bus_id:
        return {"status": "Bus not assigned"}, 400
    if latitude is None or longitude is None:
        return {"status": "Location required"}, 400

    db, cursor = get_cursor()

    try:
        cursor.execute("""
            INSERT INTO emergency_events
            (org_id, bus_id, driver_id, event_type, latitude, longitude, description)
            VALUES (%s,%s,%s,'SOS',%s,%s,%s)
        """, (org_id, bus_id, driver_id, latitude, longitude, description))

        sos_id = cursor.lastrowid

        cursor.execute("""
            SELECT id FROM users
            WHERE org_id=%s AND role='admin'
        """, (org_id,))
        admins = cursor.fetchall()

        for a in admins:
            create_notification(
                cursor=cursor,
                org_id=org_id,
                user_id=a["id"],
                role="admin",
                title="🚨 SOS Alert",
                message="Driver has sent an SOS alert.",
                reference_type="sos",
                reference_id=sos_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy
            )

        cursor.execute("""
            SELECT DISTINCT ps.parent_id
            FROM student s
            JOIN parent_student ps ON ps.student_id=s.id
            WHERE s.bus_id=%s AND s.org_id=%s
        """, (bus_id, org_id))

        parents = cursor.fetchall()
        for p in parents:
            create_notification(
                cursor=cursor,
                org_id=org_id,
                user_id=p["parent_id"],
                role="parent",
                title="🚨 Bus Emergency Alert",
                message="An emergency has been reported for your child's bus.",
                reference_type="sos",
                reference_id=sos_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy
            )

        db.commit()
        return {"status": "SOS sent successfully"}

    except Exception as e:
        db.rollback()
        print("SOS ERROR:", e)
        return {"status": "Failed to send SOS"}, 500

    finally:
        cursor.close()
        db.close()


@driver_bp.route("/student-attendance", methods=["POST"])
def student_attendance():

    if "user_id" not in session or session.get("role") != "driver":
        return {"message": "Unauthorized"}, 401

    driver_id = session["user_id"]
    org_id = session["org_id"]

    data = request.get_json() or {}
    student_id = data.get("student_id")
    action = data.get("action")   # pickup | drop
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not student_id or action not in ("pickup", "drop"):
        return {"message": "Invalid request"}, 400

    db, cursor = get_cursor()

    try:
        # =========================
        # 🔹 Get today's assignment
        # =========================
        cursor.execute("""
            SELECT bus_id, route_id
            FROM driver_assignment
            WHERE driver_id=%s
              AND org_id=%s
              AND assignment_date=CURDATE()
            LIMIT 1
        """, (driver_id, org_id))

        assign = cursor.fetchone()
        if not assign:
            return {"message": "No active assignment today"}, 400

        bus_id = assign["bus_id"]
        route_id = assign["route_id"]

        # =========================
        # 🔒 CHECK EXISTING ATTENDANCE
        # =========================
        cursor.execute("""
            SELECT status
            FROM attendance
            WHERE student_id=%s
              AND date=CURDATE()
        """, (student_id,))

        existing = cursor.fetchone()

        # 🚫 DOUBLE PICKUP BLOCK
        if action == "pickup" and existing and existing["status"] == "PICKED":
            return {"message": "Student already picked up ⚠️"}, 400

        # 🚫 DROP BEFORE PICKUP BLOCK
        if action == "drop" and (not existing or existing["status"] != "PICKED"):
            return {"message": "Pickup required before drop ⚠️"}, 400

        # =========================
        # 1️⃣ HISTORY LOG
        # =========================
        cursor.execute("""
            INSERT INTO pickup_logs
            (org_id, student_id, bus_id, driver_id,
             event_type, method, latitude, longitude)
            VALUES (%s,%s,%s,%s,%s,'manual',%s,%s)
        """, (org_id, student_id, bus_id, driver_id,
              action, lat, lng))

        # =========================
        # 2️⃣ ATTENDANCE UPDATE
        # =========================
        if action == "pickup":
            cursor.execute("""
                INSERT INTO attendance
                (student_id, route_id, pickup_time, status, date)
                VALUES (%s,%s,NOW(),'PICKED',CURDATE())
                ON DUPLICATE KEY UPDATE
                    pickup_time=NOW(),
                    status='PICKED'
            """, (student_id, route_id))

        else:  # drop
            cursor.execute("""
                UPDATE attendance
                SET drop_time=NOW(),
                    status='DROPPED'
                WHERE student_id=%s
                  AND date=CURDATE()
            """, (student_id,))

        # =========================
        # 🔔 PARENT NOTIFICATION
        # =========================
        cursor.execute("""
            SELECT s.name AS student_name, ps.parent_id
            FROM student s
            JOIN parent_student ps ON ps.student_id = s.id
            WHERE s.id = %s
        """, (student_id,))

        parents = cursor.fetchall()

        title = "🟢 Student Picked Up" if action == "pickup" else "🔵 Student Dropped"
        text  = "has been picked up and is on the way." if action == "pickup" else "has been dropped safely."

        for p in parents:
            create_notification(
                cursor=cursor,
                org_id=org_id,
                user_id=p["parent_id"],
                role="parent",
                title=title,
                message=f"{p['student_name']} {text}",
                reference_type="student",
                reference_id=student_id,
                latitude=lat,
                longitude=lng
            )

        db.commit()
        return {"message": f"{action.capitalize()} successful ✅"}

    except Exception as e:
        db.rollback()
        print("ATTENDANCE ERROR:", e)
        return {"message": "Failed ❌"}, 500

    finally:
        cursor.close()
        db.close()


#--------------
# Driver history
#---------------
@driver_bp.route("/history")
def driver_history():

    if "user_id" not in session or session.get("role") != "driver":
        return redirect("/driver/login")

    driver_id = session["user_id"]
    org_id = session.get("org_id")

    db, cursor = get_cursor()
    try:
        cursor.execute("""
            SELECT
                pl.event_time,
                pl.event_type,
                s.name AS student_name,
                s.roll_no,
                rs.stop_name
            FROM pickup_logs pl
            JOIN student s ON s.id = pl.student_id
            LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
            WHERE pl.driver_id=%s
              AND pl.org_id=%s
            ORDER BY pl.event_time DESC
        """, (driver_id, org_id))

        logs = cursor.fetchall()

        return render_template(
            "driver/driver_history.html",
            logs=logs
        )

    finally:
        cursor.close()
        db.close()
