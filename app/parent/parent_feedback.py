from flask import request, session, jsonify
from app.extensions import get_cursor
from .blueprint import parent_bp

# ======================================================
# Submit Driver Feedback (Parent)
# ======================================================
@parent_bp.route("/submit-feedback", methods=["POST"])
def submit_feedback():

    parent_id = session.get("user_id")
    org_id = session.get("org_id")

    if not parent_id:
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    student_id = request.form.get("student_id")
    driver_code = request.form.get("driver_code")
    rating = request.form.get("rating")
    message = request.form.get("message")

    if not student_id or not driver_code or not rating:
        return jsonify({
            "status": "error",
            "message": "Missing required fields"
        }), 400

    db, cursor = get_cursor()

    try:
        # ====================================
        # Get driver details
        # ====================================
        cursor.execute("""
            SELECT 
                dd.driver_id,
                COALESCE(dd.driver_full_name, u.name) AS driver_name,
                b.bus_number
            FROM driver_details dd
            LEFT JOIN users u ON u.id = dd.driver_id
            LEFT JOIN driver_assignment da 
                ON da.driver_id = dd.driver_id
                AND da.assignment_date = (
                    SELECT MAX(assignment_date)
                    FROM driver_assignment
                    WHERE driver_id = dd.driver_id
                )
            LEFT JOIN buses b ON b.id = da.bus_id
            WHERE dd.driver_code=%s
            LIMIT 1
        """, (driver_code,))

        driver_row = cursor.fetchone()

        if not driver_row:
            return jsonify({
                "status": "error",
                "message": "Driver not found"
            })

        driver_id = driver_row["driver_id"]
        driver_name = driver_row.get("driver_name") or "Unknown Driver"
        bus_number = driver_row.get("bus_number") or "N/A"

        # ====================================
        # Get student + parent info
        # ====================================
        cursor.execute("""
            SELECT 
                s.name AS student_name,
                cm.std,
                cm.division,
                u.name AS parent_name
            FROM student s
            JOIN class_master cm ON cm.id = s.class_id
            JOIN users u ON u.id = %s
            WHERE s.id = %s
        """, (parent_id, student_id))

        info = cursor.fetchone()

        student_name = info.get("student_name") if info else "Unknown Student"
        parent_name = info.get("parent_name") if info else "Unknown Parent"

        if info and info.get("std") and info.get("division"):
            student_class = f"{info.get('std')}-{info.get('division')}"
        else:
            student_class = "Unknown Class"

        # ====================================
        # Create Notification Message
        # ====================================
        notification_text = (
            f"Parent: {parent_name}, "
            f"Student: {student_name} ({student_class}), "
            f"Driver: {driver_name}, "
            f"Bus: {bus_number}, "
            f"Rating: {rating}/5, "
            f"Feedback: {message if message else 'No comment'}"
        )

        # 🔒 Prevent DB overflow
        notification_text = notification_text[:480]

        # ====================================
        # Send notification to ADMIN
        # ====================================
        cursor.execute("""
            SELECT id FROM users
            WHERE role='admin' AND org_id=%s
        """, (org_id,))

        admins = cursor.fetchall()

        for admin in admins:
            admin_id = admin["id"] if isinstance(admin, dict) else admin[0]

            cursor.execute("""
                INSERT INTO notifications
                (org_id,user_id,role,title,message,status,is_read)
                VALUES (%s,%s,'admin',%s,%s,'sent',0)
            """, (
                org_id,
                admin_id,
                "Driver Feedback Received",
                notification_text
            ))

        # ====================================
        # Send notification to DRIVER
        # ====================================
        cursor.execute("SELECT id FROM users WHERE id=%s", (driver_id,))
        if cursor.fetchone():
            cursor.execute("""
                INSERT INTO notifications
                (org_id,user_id,role,title,message,status,is_read)
                VALUES (%s,%s,'driver',%s,%s,'sent',0)
            """, (
                org_id,
                driver_id,
                "New Feedback Received",
                notification_text
            ))

        # ====================================
        # Commit
        # ====================================
        db.commit()

        return jsonify({
            "status": "success",
            "message": "Feedback submitted successfully"
        })

    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()   # 🔥 See error in terminal
        return jsonify({
            "status": "error",
            "message": str(e)
        })

    finally:
        cursor.close()
        db.close()