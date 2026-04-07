from flask import render_template, request, redirect, session, flash
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp


# =========================
# CLASS MANAGEMENT
# =========================
@org_bp.route("/classes", methods=["GET", "POST"])
@login_required
def class_manage():
    org_id = session.get("org_id")

    if not org_id:
        return redirect("/login")

    db, cursor = get_cursor()

    try:
        # -------------------------
        # ADD CLASS
        # -------------------------
        if request.method == "POST":
            std = request.form["std"]
            division = request.form["division"]

            try:
                cursor.execute("""
                    INSERT INTO class_master (org_id, std, division)
                    VALUES (%s, %s, %s)
                """, (org_id, std, division))
                db.commit()
                flash("Class added successfully", "success")
            except Exception:
                db.rollback()
                flash("Class already exists", "danger")

            return redirect("/org/classes")

        # -------------------------
        # LIST CLASSES + STUDENT COUNT
        # -------------------------
        cursor.execute("""
            SELECT 
                c.id,
                c.org_id,
                c.std,
                c.division,
                c.created_at,
                COUNT(s.id) AS student_count
            FROM class_master c
            LEFT JOIN student s
                ON s.class_id = c.id AND s.org_id = c.org_id
            WHERE c.org_id = %s
            GROUP BY c.id
            ORDER BY c.std, c.division
        """, (org_id,))
        classes = cursor.fetchall()

        return render_template(
            "org/org_class_manage.html",
            classes=classes
        )

    finally:
        cursor.close()
        db.close()


# =========================
# DELETE CLASS (SAFE)
# =========================
@org_bp.route("/classes/delete/<int:class_id>", methods=["POST"])
@login_required
def delete_class(class_id):
    org_id = session.get("org_id")

    if not org_id:
        return redirect("/login")

    db, cursor = get_cursor()

    try:
        # 1️⃣ Check if students exist for this class
        cursor.execute("""
            SELECT COUNT(*) AS student_count
            FROM student
            WHERE class_id = %s AND org_id = %s
        """, (class_id, org_id))

        result = cursor.fetchone()
        student_count = result["student_count"]

        if student_count > 0:
            flash(
                "Cannot delete class. Students are already assigned to this class.",
                "danger"
            )
            return redirect("/org/classes")

        # 2️⃣ Safe to delete class
        cursor.execute("""
            DELETE FROM class_master
            WHERE id = %s AND org_id = %s
        """, (class_id, org_id))
        db.commit()

        flash("Class deleted successfully", "success")
        return redirect("/org/classes")

    finally:
        cursor.close()
        db.close()
