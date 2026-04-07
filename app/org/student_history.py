from flask import render_template, request, session, send_file
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.extensions import login_required, get_cursor
from .blueprint import org_bp


# ==================================================
# STUDENT HISTORY PAGE (VIEW)
# ==================================================
@org_bp.route("/student-history")
@login_required
def student_history():

    # 🔐 Role check
    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]
    selected_class_id = request.args.get("class_id")

    db, cursor = get_cursor()

    # ===============================
    # FETCH CLASS LIST (for filter)
    # ===============================
    cursor.execute("""
        SELECT id, std, division
        FROM class_master
        WHERE org_id = %s
        ORDER BY std ASC, division ASC
    """, (org_id,))
    classes = cursor.fetchall()

    # ===============================
    # STUDENT HISTORY QUERY
    # ===============================
    query = """
        SELECT
            a.date,
            s.name AS student_name,
            s.roll_no,
            CONCAT(cm.std, ' ', IFNULL(cm.division,'')) AS class_category,
            b.bus_number,
            r.route_name,
            rs.stop_name,
            a.status,
            a.pickup_time,
            a.drop_time
        FROM attendance a
        JOIN student s ON a.student_id = s.id
        JOIN class_master cm ON s.class_id = cm.id
        LEFT JOIN buses b ON s.bus_id = b.id
        LEFT JOIN route_stop rs ON s.assigned_stop_id = rs.id
        LEFT JOIN routes r ON rs.route_id = r.id
        WHERE s.org_id = %s
    """

    params = [org_id]

    # ✅ Apply class filter ONLY if selected
    if selected_class_id:
        query += " AND s.class_id = %s"
        params.append(selected_class_id)

    query += " ORDER BY a.date ASC, a.pickup_time ASC"

    cursor.execute(query, params)
    history = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "org/student_history.html",
        history=history,
        classes=classes,
        selected_class_id=selected_class_id
    )


# ==================================================
# STUDENT HISTORY PDF DOWNLOAD
# ==================================================
@org_bp.route("/student-history/pdf")
@login_required
def student_history_pdf():

    # 🔐 Role check
    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]
    selected_class_id = request.args.get("class_id")

    db, cursor = get_cursor()

    # ===============================
    # SAME QUERY AS VIEW (NO LOGIC CHANGE)
    # ===============================
    query = """
        SELECT
            a.date,
            s.name AS student_name,
            s.roll_no,
            CONCAT(cm.std, ' ', IFNULL(cm.division,'')) AS class_category,
            a.status,
            a.pickup_time,
            a.drop_time
        FROM attendance a
        JOIN student s ON a.student_id = s.id
        JOIN class_master cm ON s.class_id = cm.id
        WHERE s.org_id = %s
    """

    params = [org_id]

    if selected_class_id:
        query += " AND s.class_id = %s"
        params.append(selected_class_id)

    query += " ORDER BY a.date ASC, a.pickup_time ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    cursor.close()
    db.close()

    # ===============================
    # PDF GENERATION
    # ===============================
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setTitle("Student Pickup & Drop History")

    # Header
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, height - 40, "Student Pickup & Drop History")

    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, height - 60,
        f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}")

    # Table Header
    y = height - 90
    headers = ["Date", "Student", "Roll", "Class", "Status", "Pickup", "Drop"]
    x = [40, 90, 200, 250, 320, 380, 460]

    pdf.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        pdf.drawString(x[i], y, h)

    y -= 14
    pdf.setFont("Helvetica", 9)

    # Table Rows
    for r in rows:
        if y < 60:
            pdf.showPage()
            y = height - 60
            pdf.setFont("Helvetica", 9)

        pdf.drawString(40, y, str(r["date"]))
        pdf.drawString(90, y, r["student_name"])
        pdf.drawString(200, y, str(r["roll_no"]))
        pdf.drawString(250, y, r["class_category"])
        pdf.drawString(320, y, r["status"])
        pdf.drawString(380, y, str(r["pickup_time"] or "-"))
        pdf.drawString(460, y, str(r["drop_time"] or "-"))

        y -= 12

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="student_history.pdf",
        mimetype="application/pdf"
    )
