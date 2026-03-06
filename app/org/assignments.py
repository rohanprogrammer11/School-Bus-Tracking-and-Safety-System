from flask import render_template, request, redirect, session, flash
from datetime import date, timedelta
import uuid
from app.utils.notification_service import create_notification
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp


# =====================================================
# DATE HELPER
# =====================================================
def get_next_assignment_date(current_date):
    next_date = current_date + timedelta(days=1)
    if next_date.weekday() == 6:  # Sunday
        next_date += timedelta(days=1)
    return next_date


# =====================================================
# ASSIGN DRIVER
# =====================================================
@org_bp.route("/assign-driver", methods=["GET", "POST"])
@login_required
def assign_driver():
    org_id = session["org_id"]
    db, cursor = get_cursor()

    try:
        if request.method == "POST":
            driver_id = int(request.form["driver_id"])
            bus_id = int(request.form["bus_id"])
            route_id = int(request.form["route_id"])
            assignment_type = request.form["assignment_type"]
            assign_date = date.fromisoformat(request.form["date"])
            assignment_code = request.form["assignment_code"].strip()
            status = "ASSIGNED"

            # ---------------- DRIVER CHECK ----------------
            cursor.execute(
                "SELECT status FROM driver_details WHERE driver_id=%s",
                (driver_id,)
            )
            row = cursor.fetchone()
            if not row or row["status"] != "ACTIVE":
                flash("Cannot assign: Driver inactive.", "error")
                return redirect("/org/assign-driver")

            # ---------------- BUS CHECK ----------------
            cursor.execute(
                "SELECT status FROM buses WHERE id=%s AND org_id=%s",
                (bus_id, org_id)
            )
            row = cursor.fetchone()
            if not row or row["status"] != "ACTIVE":
                flash("Cannot assign: Bus inactive.", "error")
                return redirect("/org/assign-driver")

            # ---------------- ROUTE TIME ----------------
            cursor.execute(
                "SELECT start_time, drop_time FROM routes WHERE id=%s AND org_id=%s",
                (route_id, org_id)
            )
            times = cursor.fetchone()
            pickup_time = times["start_time"]
            drop_time = times["drop_time"]

            # ---------------- UPSERT ----------------
            def upsert_assignment(assign_kind, assign_time):
                cursor.execute("""
                    INSERT INTO driver_assignment
                    (assignment_code, org_id, driver_id, bus_id, route_id,
                     assignment, assignment_date, assignment_time, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        assignment_date = VALUES(assignment_date),
                        assignment_time = VALUES(assignment_time),
                        bus_id = VALUES(bus_id),
                        route_id = VALUES(route_id),
                        status = VALUES(status)
                """, (
                    assignment_code,
                    org_id,
                    driver_id,
                    bus_id,
                    route_id,
                    assign_kind,
                    assign_date,
                    assign_time,
                    status
                ))

            # ---------------- APPLY ----------------
            if assignment_type in ("PICKUP", "DROP"):
                upsert_assignment(
                    assignment_type,
                    pickup_time if assignment_type == "PICKUP" else drop_time
                )
            else:
                upsert_assignment("PICKUP", pickup_time)
                upsert_assignment("DROP", drop_time)

            # 🔔 NOTIFY DRIVER
            create_notification(
                cursor,
                org_id,
                driver_id,
                "driver",
                "New Assignment",
                f"You have been assigned a {assignment_type} route on {assign_date}",
                reference_type="assignment",
                reference_id=None
            )

            db.commit()
            flash("Driver assignment saved successfully.", "success")
            return redirect("/org/assign-driver")

        # ================= LOAD PAGE =================
        cursor.execute("""
            SELECT u.id, u.name, d.status
            FROM users u
            JOIN driver_details d ON d.driver_id=u.id
            WHERE u.org_id=%s AND u.role='driver'
        """, (org_id,))
        drivers = cursor.fetchall()

        cursor.execute("""
            SELECT id, bus_number, status
            FROM buses
            WHERE org_id=%s
        """, (org_id,))
        buses = cursor.fetchall()

        cursor.execute("""
            SELECT id, route_name
            FROM routes
            WHERE org_id=%s
        """, (org_id,))
        routes = cursor.fetchall()

        cursor.execute("""
            SELECT driver_id, assignment
            FROM driver_assignment
            WHERE org_id=%s AND assignment_date=%s
        """, (org_id, date.today()))

        daily_assignments = {}
        for row in cursor.fetchall():
            daily_assignments.setdefault(row["driver_id"], []).append(row["assignment"])

        return render_template(
            "org/assign_driver.html",
            drivers=drivers,
            buses=buses,
            routes=routes,
            today=date.today().strftime("%Y-%m-%d"),
            daily_assignments=daily_assignments
        )

    finally:
        cursor.close()
        db.close()


# =====================================================
# AUTO ROLL ASSIGNMENTS
# =====================================================
def auto_roll_assignments(cursor, org_id):
    today = date.today()

    cursor.execute("""
        SELECT id, driver_id, assignment, assignment_date
        FROM driver_assignment
        WHERE org_id=%s AND status='ASSIGNED'
    """, (org_id,))

    for row in cursor.fetchall():
        assignment_id = row["id"]
        driver_id = row["driver_id"]
        assignment = row["assignment"]
        old_date = row["assignment_date"]

        if old_date == today:
            continue

        if old_date < today:
            new_date = old_date
            while new_date < today:
                new_date = get_next_assignment_date(new_date)

            cursor.execute("""
                UPDATE driver_assignment
                SET assignment_date=%s
                WHERE id=%s
            """, (new_date, assignment_id))

            if new_date == today:
                cursor.execute("""
                    SELECT COUNT(*) AS cnt
                    FROM notifications
                    WHERE user_id=%s
                      AND role='driver'
                      AND title="Today's Assignment"
                      AND reference_id=%s
                """, (driver_id, assignment_id))

                if cursor.fetchone()["cnt"] == 0:
                    create_notification(
                        cursor,
                        org_id,
                        driver_id,
                        "driver",
                        "Today's Assignment",
                        f"You have a {assignment} assignment scheduled for today.",
                        reference_type="assignment",
                        reference_id=assignment_id
                    )


# =====================================================
# VIEW ASSIGNMENTS
# =====================================================
@org_bp.route("/assignments")
@login_required
def org_assignments_view():
    org_id = session["org_id"]
    db, cursor = get_cursor()

    try:
        auto_roll_assignments(cursor, org_id)
        db.commit()

        cursor.execute("""
            SELECT 
                da.id,
                da.assignment_code,
                u.name AS driver_name,
                b.bus_number,
                r.route_name,
                r.start_point,
                r.end_point,
                da.assignment,
                da.assignment_time,
                da.assignment_date
            FROM driver_assignment da
            JOIN users u ON u.id = da.driver_id
            JOIN buses b ON b.id = da.bus_id
            JOIN routes r ON r.id = da.route_id
            WHERE da.org_id=%s
            ORDER BY da.assignment_date DESC
        """, (org_id,))

        assignments = []
        for r in cursor.fetchall():
            if isinstance(r["assignment_time"], timedelta):
                seconds = int(r["assignment_time"].total_seconds())
                h = seconds // 3600
                m = (seconds % 3600) // 60
                r["assignment_time"] = f"{(h % 12 or 12):02d}:{m:02d} {'AM' if h < 12 else 'PM'}"
            assignments.append(r)

        return render_template(
            "org/org_assignments_view.html",
            assignments=assignments
        )

    finally:
        cursor.close()
        db.close()


# =====================================================
# REMOVE ASSIGNMENT
# =====================================================
@org_bp.route("/assign-driver/<int:assignment_id>/remove", methods=["POST"])
@login_required
def remove_assignment(assignment_id):
    org_id = session["org_id"]
    db, cursor = get_cursor()

    try:
        cursor.execute("""
            DELETE FROM driver_assignment
            WHERE id=%s AND org_id=%s
        """, (assignment_id, org_id))

        db.commit()
        flash("Assignment removed.", "success")
        return redirect(request.referrer or "/org/assignments")

    finally:
        cursor.close()
        db.close()


# =====================================================
# EDIT ASSIGNMENT
# =====================================================
@org_bp.route("/assign-driver/<int:assignment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assignment(assignment_id):
    org_id = session["org_id"]
    db, cursor = get_cursor()

    try:
        if request.method == "POST":
            cursor.execute("""
                UPDATE driver_assignment
                SET driver_id=%s,
                    bus_id=%s,
                    route_id=%s,
                    assignment=%s,
                    assignment_date=%s,
                    assignment_time=%s
                WHERE id=%s AND org_id=%s
            """, (
                request.form["driver_id"],
                request.form["bus_id"],
                request.form["route_id"],
                request.form["assignment"],
                request.form["date"],
                request.form["time"],
                assignment_id,
                org_id
            ))

            db.commit()
            flash("Assignment updated successfully.", "success")
            return redirect("/org/assignments")

        cursor.execute("""
            SELECT 
                da.id,
                da.assignment_code,
                da.driver_id,
                u.name AS driver_name,
                da.bus_id,
                da.route_id,
                da.assignment,
                da.assignment_date,
                da.assignment_time
            FROM driver_assignment da
            JOIN users u ON u.id = da.driver_id
            WHERE da.id=%s AND da.org_id=%s
        """, (assignment_id, org_id))

        r = cursor.fetchone()

        assignment = {
            "id": r["id"],
            "assignment_code": r["assignment_code"],
            "driver_id": r["driver_id"],
            "driver_name": r["driver_name"],
            "bus_id": r["bus_id"],
            "route_id": r["route_id"],
            "assignment": r["assignment"],
            "assignment_date": r["assignment_date"].strftime("%Y-%m-%d"),
            "assignment_time": (
                f"{(r['assignment_time'].seconds // 3600):02d}:"
                f"{((r['assignment_time'].seconds % 3600) // 60):02d}"
                if isinstance(r["assignment_time"], timedelta) else ""
            )
        }

        cursor.execute("""
            SELECT u.id, u.name, d.status
            FROM users u
            JOIN driver_details d ON d.driver_id=u.id
            WHERE u.org_id=%s AND u.role='driver'
        """, (org_id,))
        drivers = cursor.fetchall()

        cursor.execute("""
            SELECT id, bus_number
            FROM buses
            WHERE org_id=%s AND status='ACTIVE'
        """, (org_id,))
        buses = cursor.fetchall()

        cursor.execute("""
            SELECT id, route_name
            FROM routes
            WHERE org_id=%s
        """, (org_id,))
        routes = cursor.fetchall()

        return render_template(
            "org/edit_assignment.html",
            assignment=assignment,
            drivers=drivers,
            buses=buses,
            routes=routes
        )

    finally:
        cursor.close()
        db.close()
