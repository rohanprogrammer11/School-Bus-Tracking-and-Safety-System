from flask import render_template, session
from app.extensions import login_required, get_cursor
from app.parent.blueprint import parent_bp
from app.utils.notification_service import (
    get_notifications,
    mark_all_as_read
)

# ==========================
# PARENT NOTIFICATIONS
# ==========================
@parent_bp.route("/notifications")
@login_required
def parent_notifications():

    # 🔒 Only parent can access
    if session.get("role") != "parent":
        return "Unauthorized", 403

    # Session data
    user_id = session["user_id"]
    org_id = session["org_id"]
    role = "parent"

    # DB connection
    db, cursor = get_cursor()

    try:
        # 📥 Fetch notifications
        notifications = get_notifications(
            cursor,
            user_id,
            role,
            org_id
        )

        # ✅ Mark all as read AFTER fetching
        mark_all_as_read(
            cursor,
            user_id,
            role,
            org_id
        )

        db.commit()

        # 🖥️ Render notifications page
        return render_template(
            "/notifications.html",
            notifications=notifications,
            role=role
        )

    finally:
        # 🔚 Close DB safely
        cursor.close()
        db.close()


@parent_bp.route("/notifications/unread-count")
@login_required
def parent_unread_notification_count():

    if session.get("role") != "parent":
        return {"count": 0}, 403

    user_id = session["user_id"]
    org_id = session["org_id"]
    role = "parent"

    db, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM notifications
            WHERE user_id = %s
              AND role = %s
              AND org_id = %s
              AND is_read = 0
        """, (user_id, role, org_id))

        row = cursor.fetchone()
        count = row["count"] if row and "count" in row else 0
        return {"count": count}

    finally:
        cursor.close()
        db.close()
