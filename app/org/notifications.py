from flask import redirect, render_template, session, request, flash
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
from app.utils.notification_service import (
    get_notifications,
    mark_all_as_read
)

# ==========================
# ORGANIZATION NOTIFICATIONS
# ==========================
@org_bp.route("/notifications")
@login_required
def org_notifications():

    # only org admin
    if session.get("role") != "admin":
        return "Unauthorized", 403

    user_id = session["user_id"]
    org_id = session["org_id"]
    role = "admin"

    db, cursor = get_cursor()

    try:
        # 🔔 COUNT MODE
        if request.args.get("count"):
            cursor.execute("""
                SELECT COUNT(*) AS unread
                FROM notifications
                WHERE user_id=%s
                  AND role=%s
                  AND org_id=%s
                  AND is_read=0
            """, (user_id, role, org_id))

            row = cursor.fetchone()
            return {"unread": row["unread"]}

        notifications = get_notifications(cursor, user_id, role, org_id)
        mark_all_as_read(cursor, user_id, role, org_id)
        db.commit()

        return render_template(
            "notifications.html",
            notifications=notifications,
            role=role
        )

    finally:
        cursor.close()
        db.close()


# ==========================
# SEND NOTICE (ORG → DRIVER / PARENT)
# ==========================
@org_bp.route("/send-notice", methods=["GET", "POST"])
@login_required
def send_notice():

    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session.get("org_id")
    if not org_id:
        return "Unauthorized", 403

    db, cursor = get_cursor()

    try:
        if request.method == "POST":
            title = request.form.get("title")
            message = request.form.get("message") or ""
            target_role = request.form.get("target_role")

            if not title or not message or target_role not in ("driver", "parent", "both"):
                return "Invalid data", 400

            roles = ["driver", "parent"] if target_role == "both" else [target_role]

            for role in roles:
                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE role=%s AND org_id=%s
                """, (role, org_id))

                users = cursor.fetchall()

                for u in users:
                    cursor.execute("""
                        INSERT INTO notifications (
                            org_id,
                            user_id,
                            role,
                            title,
                            message,
                            status,
                            is_read
                        )
                        VALUES (%s, %s, %s, %s, %s, 'sent', 0)
                    """, (
                        org_id,
                        u["id"],
                        role,
                        title,
                        message
                    ))

            db.commit()
            flash("Notice sent successfully!", "success")
            return redirect(request.url)   # stay on same page

        return render_template("org/org_send_notice.html")

    finally:
        cursor.close()
        db.close()
