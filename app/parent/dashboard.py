from flask import flash, jsonify, redirect, render_template, request, session, url_for
from datetime import date
from werkzeug.security import generate_password_hash
from app.extensions import login_required, get_cursor
from .blueprint import parent_bp
import secrets
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib


def get(row, key_or_index):
    """
    Safe accessor:
    - Works for dict cursor (dictionary=True)
    - Works for tuple cursor
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key_or_index)
    return row[key_or_index]


# ==================================================
# PARENT DASHBOARD
# ==================================================
@parent_bp.route("/dashboard")
@login_required
def parent_dashboard():

    db, cursor = get_cursor()
    parent_id = session["user_id"]
    today = date.today()

    # ===============================
    # ORGANIZATION PHONE (FALLBACK)
    # ===============================
    cursor.execute("""
        SELECT phone
        FROM organization
        ORDER BY id ASC
        LIMIT 1
    """)
    org_row = cursor.fetchone()
    org_phone = get(org_row, "phone" if isinstance(org_row, dict) else 0) if org_row else "N/A"

    # ===============================
    # STUDENTS
    # ===============================
    cursor.execute("""
        SELECT
            s.id            AS student_id,
            s.name          AS student_name,
            s.roll_no,
            s.bus_id,
            b.bus_number,
            r.route_name,
            rs.stop_name
        FROM parent_student ps
        JOIN student s ON ps.student_id = s.id
        LEFT JOIN buses b ON s.bus_id = b.id
        LEFT JOIN route_stop rs ON s.assigned_stop_id = rs.id
        LEFT JOIN routes r ON rs.route_id = r.id
        WHERE ps.parent_id = %s
    """, (parent_id,))
    students_raw = cursor.fetchall()

    students = []
    for r in students_raw:
        students.append({
            "id": get(r, "student_id" if isinstance(r, dict) else 0),
            "name": get(r, "student_name" if isinstance(r, dict) else 1),
            "roll_no": get(r, "roll_no" if isinstance(r, dict) else 2),
            "bus_id": get(r, "bus_id" if isinstance(r, dict) else 3),
            "bus_number": get(r, "bus_number" if isinstance(r, dict) else 4),
            "route_name": get(r, "route_name" if isinstance(r, dict) else 5),
            "stop_name": get(r, "stop_name" if isinstance(r, dict) else 6),
        })

    # ===============================
    # TODAY ATTENDANCE
    # ===============================
    cursor.execute("""
        SELECT
            a.student_id,
            a.status,
            a.pickup_time,
            a.drop_time
        FROM attendance a
        JOIN parent_student ps ON ps.student_id = a.student_id
        WHERE ps.parent_id = %s
          AND a.date = %s
    """, (parent_id, today))

    attendance_map = {}
    for r in cursor.fetchall():
        sid = get(r, "student_id" if isinstance(r, dict) else 0)
        attendance_map[sid] = {
            "status": get(r, "status" if isinstance(r, dict) else 1),
            "pickup_time": get(r, "pickup_time" if isinstance(r, dict) else 2),
            "drop_time": get(r, "drop_time" if isinstance(r, dict) else 3),
        }

    # ===============================
    # ATTENDANCE HISTORY (LAST 30)
    # ===============================
    cursor.execute("""
        SELECT
            a.student_id,
            a.date,
            a.status,
            a.pickup_time,
            a.drop_time
        FROM attendance a
        JOIN parent_student ps ON ps.student_id = a.student_id
        WHERE ps.parent_id = %s
        ORDER BY a.date DESC
        LIMIT 30
    """, (parent_id,))

    attendance_history_map = {}
    for r in cursor.fetchall():
        sid = get(r, "student_id" if isinstance(r, dict) else 0)
        attendance_history_map.setdefault(sid, []).append({
            "date": get(r, "date" if isinstance(r, dict) else 1),
            "status": get(r, "status" if isinstance(r, dict) else 2),
            "pickup_time": get(r, "pickup_time" if isinstance(r, dict) else 3),
            "drop_time": get(r, "drop_time" if isinstance(r, dict) else 4),
        })

    # ===============================
    # LIVE BUS LOCATION
    # ===============================
    cursor.execute("""
        SELECT
            lu.bus_id,
            lu.latitude,
            lu.longitude,
            lu.speed,
            lu.event_time
        FROM location_update lu
        WHERE lu.event_time = (
            SELECT MAX(event_time)
            FROM location_update
            WHERE bus_id = lu.bus_id
        )
    """)

    location_map = {}
    for r in cursor.fetchall():
        bid = get(r, "bus_id" if isinstance(r, dict) else 0)
        location_map[bid] = {
            "latitude": get(r, "latitude" if isinstance(r, dict) else 1),
            "longitude": get(r, "longitude" if isinstance(r, dict) else 2),
            "speed": get(r, "speed" if isinstance(r, dict) else 3),
            "time": get(r, "event_time" if isinstance(r, dict) else 4),
        }

    # ===============================
    # DRIVER DETAILS (LATEST)
    # ===============================
    cursor.execute("""
        SELECT
            b.id AS bus_id,
            dd.driver_code,
            COALESCE(dd.driver_full_name, u.name) AS driver_name,
            COALESCE(dd.mobile_number, u.phone) AS driver_phone
        FROM buses b
        LEFT JOIN driver_assignment da ON da.bus_id = b.id
        LEFT JOIN users u ON u.id = da.driver_id
        LEFT JOIN driver_details dd ON dd.driver_id = da.driver_id
        WHERE da.assignment_date = (
            SELECT MAX(da2.assignment_date)
            FROM driver_assignment da2
            WHERE da2.bus_id = b.id
        )
    """)

    driver_map = {}
    for r in cursor.fetchall():
        bus_id = get(r, "bus_id" if isinstance(r, dict) else 0)
        driver_map[bus_id] = {
            "code": get(r, "driver_code" if isinstance(r, dict) else 1),
            "name": get(r, "driver_name" if isinstance(r, dict) else 2),
            "phone": get(r, "driver_phone" if isinstance(r, dict) else 3),
        }

    # ===============================
    # ORGANIZATION DETAILS (CORRECT)
    # ===============================
    cursor.execute("""
        SELECT o.org_name, o.phone
        FROM organization o
        JOIN users u ON u.org_id = o.id
        WHERE u.id = %s
        LIMIT 1
    """, (parent_id,))

    org_row = cursor.fetchone()

    org_name = get(org_row, "org_name" if isinstance(org_row, dict) else 0) if org_row else "School"
    org_phone = get(org_row, "phone" if isinstance(org_row, dict) else 1) if org_row else "N/A"



    cursor.close()
    db.close()

    return render_template(
        "parent/parent_dashboard.html",
        students=students,
        attendance_map=attendance_map,
        attendance_history_map=attendance_history_map,
        location_map=location_map,
        driver_map=driver_map,
        org_phone=org_phone,
        org_name=org_name
    )



# ==================================================
# LIVE MAP PAGE
# ==================================================
@parent_bp.route("/live-map/<int:bus_id>")
@login_required
def parent_live_map(bus_id):

    parent_id = session.get("user_id")

    db, cursor = get_cursor()

    # ✅ Check if parent owns this bus
    cursor.execute("""
        SELECT s.bus_id
        FROM student s
        JOIN parent_student ps ON ps.student_id = s.id
        WHERE ps.parent_id = %s AND s.bus_id = %s
    """, (parent_id, bus_id))

    if not cursor.fetchone():
        return "Unauthorized", 403

    # ✅ Get route stops
    cursor.execute("""
        SELECT rs.stop_name, rs.latitude, rs.longitude
        FROM route_stop rs
        JOIN student s ON s.assigned_stop_id = rs.id
        JOIN parent_student ps ON ps.student_id = s.id
        WHERE ps.parent_id = %s AND s.bus_id = %s
        ORDER BY rs.stop_order
    """, (parent_id, bus_id))

    stops = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "parent/parent_live_map.html",
        bus_id=bus_id,
        stops=stops
    )


# ==================================================
# BUS LOCATION API
# ==================================================
@parent_bp.route("/bus-location/<int:bus_id>")
@login_required
def parent_bus_location(bus_id):

    parent_id = session.get("user_id")

    db, cursor = get_cursor()

    # ✅ Security check
    cursor.execute("""
        SELECT s.bus_id
        FROM student s
        JOIN parent_student ps ON ps.student_id = s.id
        WHERE ps.parent_id = %s AND s.bus_id = %s
    """, (parent_id, bus_id))

    if not cursor.fetchone():
        return {"error": "Unauthorized"}, 403

    # ✅ Get latest location
    cursor.execute("""
        SELECT latitude, longitude
        FROM location_update
        WHERE bus_id = %s
        ORDER BY event_time DESC
        LIMIT 1
    """, (bus_id,))

    data = cursor.fetchone()

    cursor.close()
    db.close()

    return data or {}


# ==================================================
# BUS ROUTE API
# ==================================================
@parent_bp.route("/bus-route/<int:bus_id>")
@login_required
def parent_bus_route(bus_id):

    parent_id = session.get("user_id")

    db, cursor = get_cursor()

    # ✅ Security check
    cursor.execute("""
        SELECT s.bus_id
        FROM student s
        JOIN parent_student ps ON ps.student_id = s.id
        WHERE ps.parent_id = %s AND s.bus_id = %s
    """, (parent_id, bus_id))

    if not cursor.fetchone():
        return {"error": "Unauthorized"}, 403

    # ✅ Get stops
    cursor.execute("""
        SELECT rs.stop_name AS name, rs.latitude, rs.longitude
        FROM route_stop rs
        JOIN student s ON s.assigned_stop_id = rs.id
        JOIN parent_student ps ON ps.student_id = s.id
        WHERE ps.parent_id = %s AND s.bus_id = %s
        ORDER BY rs.stop_order
    """, (parent_id, bus_id))

    stops = cursor.fetchall()

    cursor.close()
    db.close()

    return jsonify(stops)

#----------------------
#
#------------------------
@parent_bp.route("/forgot-password", methods=["GET", "POST"])
def parent_forgot_password():

    if request.method == "POST":
        email = request.form.get("email")

        db, cursor = get_cursor()

        cursor.execute("""
            SELECT id FROM users
            WHERE email = %s AND role = 'parent'
        """, (email,))
        parent = cursor.fetchone()

        if not parent:
            flash("Email not registered as parent.", "error")
            cursor.close()
            db.close()
            return redirect(url_for("parent.parent_forgot_password"))

        # Generate token
        token = secrets.token_urlsafe(32)
        expiry = datetime.now() + timedelta(minutes=15)

        cursor.execute("""
            UPDATE users
            SET reset_token = %s,
                reset_expiry = %s
            WHERE id = %s
        """, (token, expiry, parent["id"]))

        db.commit()

        reset_link = url_for(
            "parent.parent_reset_password",
            token=token,
            _external=True
        )

        # Send Email
        msg = EmailMessage()
        msg["Subject"] = "Parent Password Reset"
        msg["From"] = "schoolbustracking000@gmail.com"
        msg["To"] = email
        msg.set_content(f"""
Click the link below to reset your password:

{reset_link}

This link will expire in 15 minutes.
""")

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login("schoolbustracking000@gmail.com", "fohu hszp uqpq axng")
                server.send_message(msg)
        except Exception as e:
            print("Email Error:", e)

        flash("Reset link sent to your email.", "success")

        cursor.close()
        db.close()

        return redirect(url_for("parent.parent_forgot_password"))

    return render_template("forgot_password.html")



#-------------------------
#
#-------------------------
@parent_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def parent_reset_password(token):

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT id, reset_expiry
        FROM users
        WHERE reset_token = %s AND role = 'parent'
    """, (token,))
    parent = cursor.fetchone()

    if not parent:
        flash("Invalid or expired reset link.", "error")
        cursor.close()
        db.close()
        return redirect(url_for("parent.parent_forgot_password"))

    # Expiry check
    if parent["reset_expiry"] < datetime.now():
        flash("Reset link expired.", "error")
        cursor.close()
        db.close()
        return redirect(url_for("parent.parent_forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")

        import re

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[A-Z]', new_password):
            flash("Must contain uppercase letter.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[a-z]', new_password):
            flash("Must contain lowercase letter.", "error")
            return render_template("reset_password.html")

        if not re.search(r'\d', new_password):
            flash("Must contain number.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', new_password):
            flash("Must contain special character.", "error")
            return render_template("reset_password.html")

        from werkzeug.security import generate_password_hash

        hashed_password = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password_hash = %s,
                reset_token = NULL,
                reset_expiry = NULL
            WHERE id = %s
        """, (hashed_password, parent["id"]))

        db.commit()

        flash("Password reset successful. Please login.", "success")

        cursor.close()
        db.close()

        return redirect(url_for("auth.parent_login"))

    cursor.close()
    db.close()

    return render_template("reset_password.html")



# ============================================
# ASSIGN STUDENT TO PARENT
# ============================================
@parent_bp.route("/assign-student", methods=["POST"])
@login_required
def assign_student():

    # if admin sends parent_id use it
    # else fallback to logged-in parent
    parent_id = request.form.get("parent_id") or session.get("user_id")
    student_id = request.form.get("student_id")

    if not student_id:
        return jsonify({"status": "error", "message": "Student not selected"})

    db, cursor = get_cursor()

    try:
        # prevent duplicate (ANY parent)
        cursor.execute("""
            SELECT 1 FROM parent_student
            WHERE student_id = %s
        """, (student_id,))

        if cursor.fetchone():
            return jsonify({
                "status": "error",
                "message": "Student already assigned to another parent"
            })

        cursor.execute("""
            INSERT INTO parent_student (parent_id, student_id)
            VALUES (%s, %s)
        """, (parent_id, student_id))

        db.commit()

        return jsonify({
            "status": "success",
            "message": "Student assigned successfully"
        })

    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)})

    finally:
        cursor.close()
        db.close()


@parent_bp.route("/assign-page")
@login_required
def assign_page():

    db, cursor = get_cursor()

    cursor.execute("SELECT id, name FROM users WHERE role='parent'")
    parents = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("parent/assign_student.html", parents=parents)

@parent_bp.route("/find-student", methods=["POST"])
@login_required
def find_student():

    data = request.get_json()
    value = data.get("value")

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT s.id, s.name, s.roll_no, s.rfid_tag, s.qr_code,
               cm.std, cm.division
        FROM student s
        JOIN class_master cm ON s.class_id = cm.id
        WHERE s.roll_no = %s
           OR s.rfid_tag = %s
           OR s.qr_code = %s
        LIMIT 1
    """, (value, value, value))

    student = cursor.fetchone()

    cursor.close()
    db.close()

    if not student:
        return jsonify({
            "status": "error",
            "message": "Student not found"
        })

    return jsonify({
        "status": "success",
        "student": student
    })


@parent_bp.route("/assign-student-full", methods=["POST"])
@login_required
def assign_student_full():

    parent_id = request.form.get("parent_id")
    roll_no = request.form.get("roll_no")
    rfid = request.form.get("rfid_tag")
    qr = request.form.get("qr_code")

    db, cursor = get_cursor()

    try:
        # find student
        cursor.execute("""
            SELECT id FROM student
            WHERE roll_no=%s OR rfid_tag=%s OR qr_code=%s
            LIMIT 1
        """, (roll_no, rfid, qr))

        student = cursor.fetchone()

        if not student:
            return "❌ Student not found"

        student_id = student["id"]

        # check already assigned
        cursor.execute("SELECT 1 FROM parent_student WHERE student_id=%s", (student_id,))
        if cursor.fetchone():
            return "❌ Already assigned"

        # assign
        cursor.execute("""
            INSERT INTO parent_student (parent_id, student_id)
            VALUES (%s,%s)
        """, (parent_id, student_id))

        db.commit()

        return redirect("/parent/profile")

    except Exception as e:
        db.rollback()
        return str(e)

    finally:
        cursor.close()
        db.close()