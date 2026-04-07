from flask import render_template, session, request
from app.extensions import login_required, get_cursor
from app.driver.blueprint import driver_bp
from flask import jsonify, session
from app.utils.notification_service import (
    get_notifications,
    mark_all_as_read,
    create_notification
)

# =========================
# DRIVER NOTIFICATIONS PAGE
# =========================
@driver_bp.route("/notifications")
@login_required
def driver_notifications():

    if session.get("role") != "driver":
        return "Unauthorized", 403

    user_id = session["user_id"]
    org_id = session["org_id"]
    role = "driver"

    db, cursor = get_cursor()

    try:
        notifications = get_notifications(cursor, user_id, role, org_id)
        mark_all_as_read(cursor, user_id, role, org_id)
        db.commit()

        return render_template(
            "/notifications.html",
            notifications=notifications,
            role=role
        )

    finally:
        cursor.close()
        db.close()


# =========================
# UNREAD COUNT (LIVE BADGE)
# =========================
@driver_bp.route("/notifications/unread-count")
@login_required
def unread_notification_count():
    user_id = session.get("user_id")
    conn, cursor = get_cursor()

    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE user_id=%s AND role='driver' AND is_read=0
    """,(user_id,))

    row = cursor.fetchone()
    return jsonify({"count": row["count"] if row else 0})

# =========================
# QUICK DRIVER ALERT
# =========================
@driver_bp.route("/send-quick-alert", methods=["POST"])
@login_required
def send_quick_alert():

    if session.get("role") != "driver":
        return {"status": "Unauthorized"}, 401

    driver_id = session["user_id"]
    org_id = session["org_id"]

    data = request.get_json(silent=True) or {}
    message = data.get("message")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")

    if not message:
        return {"status": "Message required"}, 400

    db, cursor = get_cursor()

    try:
        # =========================
        # ORG ADMINS ONLY
        # =========================
        cursor.execute("""
            SELECT id
            FROM users
            WHERE org_id=%s AND role='admin'
        """, (org_id,))
        admins = cursor.fetchall()

        for admin in admins:
            create_notification(
                cursor=cursor,
                org_id=org_id,
                user_id=admin["id"],
                role="admin",
                title="🚌 Driver Update",
                message=message,
                reference_type="driver_alert",
                reference_id=driver_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy
            )


        db.commit()
        return {"status": "Message sent to organization"}

    except Exception as e:
        db.rollback()
        print("Quick Alert Error:", e)
        return {"status": "Failed"}, 500

    finally:
        cursor.close()
        db.close()

@driver_bp.route("/notifications/mark-read",methods=["POST"])
@login_required
def mark_read():
    user_id = session.get("user_id")
    conn, cursor = get_cursor()

    cursor.execute("""
        UPDATE notifications
        SET is_read=1
        WHERE user_id=%s AND role='driver'
    """,(user_id,))
    conn.commit()
    return "",204