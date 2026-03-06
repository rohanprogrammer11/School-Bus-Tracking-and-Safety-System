from flask import render_template, request, session, redirect, url_for
from app.extensions import login_required, get_cursor
from app.parent.blueprint import parent_bp


@parent_bp.route("/profile")
@login_required
def parent_profile():

    # 🔐 Role check
    if session.get("role") != "parent":
        return redirect(url_for("auth.landing"))

    parent_id = session["user_id"]
    org_id = session["org_id"]

    db, cursor = get_cursor()

    # =========================
    # Parent details
    # =========================
    cursor.execute("""
        SELECT id, name, email, phone
        FROM users
        WHERE id = %s AND role = 'parent'
    """, (parent_id,))
    parent = cursor.fetchone()

    # =========================
    # Children details
    # =========================
    cursor.execute("""
        SELECT
            s.id AS student_id,
            s.name AS student_name,
            s.roll_no,
            cm.std,
            cm.division,
            b.bus_number,
            r.route_name,
            rs.stop_name,
            s.bus_id
        FROM student s
        JOIN class_master cm ON cm.id = s.class_id
        LEFT JOIN buses b ON b.id = s.bus_id
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
        LEFT JOIN routes r ON r.id = rs.route_id
        WHERE s.parent_id = %s
          AND s.org_id = %s
        ORDER BY s.name
    """, (parent_id, org_id))

    students = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "parent/parent_profile.html",
        parent=parent,
        students=students,
        attendance_map={},   # future use
        location_map={}
    )

