from flask import render_template, request, redirect, session, flash, jsonify
from mysql.connector import IntegrityError
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask import Response
import io
from datetime import datetime
from decimal import Decimal



# =========================
# STUDENT LIST (ONLY)
# =========================
@org_bp.route("/students", methods=["GET"])
@login_required
def student_manage():
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    selected_class_id = request.args.get("class_id")

    # =========================
    # DROPDOWNS
    # =========================
    cursor.execute(
        "SELECT id, std, division FROM class_master WHERE org_id=%s",
        (org_id,)
    )
    classes = cursor.fetchall()

    cursor.execute(
        "SELECT id, name FROM users WHERE org_id=%s AND role='parent'",
        (org_id,)
    )
    parents = cursor.fetchall()

    cursor.execute(
        "SELECT id, bus_number FROM buses WHERE org_id=%s AND status='ACTIVE'",
        (org_id,)
    )
    buses = cursor.fetchall()

    # =========================
    # STUDENT LIST + FEE
    # =========================
    query = """
        SELECT 
            s.id,
            s.name,
            s.roll_no,
            s.rfid_tag,
            s.qr_code,
            c.std,
            c.division,

            COALESCE(p1.name, p2.name) AS parent_name,
            COALESCE(p1.phone, p2.phone) AS parent_phone,

            b.bus_number,
            d.name AS driver_name,
            r.route_name,
            r.start_time AS pickup_time,
            r.drop_time AS drop_time,
            rs.stop_name,

            -- 💰 BUS FEE
            rs.monthly_fee AS total_fee,
            IFNULL(f.amount_paid, 0) AS amount_paid,
            IFNULL(rs.monthly_fee, 0) - IFNULL(f.amount_paid, 0) AS remaining_fee

        FROM student s
        JOIN class_master c ON c.id = s.class_id

        LEFT JOIN users p1 
            ON p1.id = s.parent_id AND p1.role='parent'

        LEFT JOIN parent_student ps ON ps.student_id = s.id
        LEFT JOIN users p2 
            ON p2.id = ps.parent_id AND p2.role='parent'

        LEFT JOIN buses b ON b.id = s.bus_id

        LEFT JOIN driver_assignment da
            ON da.id = (
                SELECT MAX(id)
                FROM driver_assignment
                WHERE bus_id = b.id AND status='ASSIGNED'
            )

        LEFT JOIN users d ON d.id = da.driver_id
        LEFT JOIN routes r ON r.id = da.route_id
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id

        LEFT JOIN student_bus_fee f
            ON f.student_id = s.id
            AND f.billing_month = DATE_FORMAT(CURDATE(), '%Y-%m-01')

        WHERE s.org_id=%s
    """

    params = [org_id]

    if selected_class_id:
        query += " AND s.class_id=%s"
        params.append(selected_class_id)

    query += " ORDER BY c.std, c.division, s.roll_no"

    cursor.execute(query, tuple(params))
    students = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "org/org_student_manage.html",
        classes=classes,
        parents=parents,
        buses=buses,
        students=students
    )


# =========================
# ADD STUDENT
# =========================
@org_bp.route("/students/add", methods=["GET", "POST"])
@login_required
def add_student():
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    if request.method == "POST":
        try:
            parent_id = request.form.get("parent_id") or None

            cursor.execute("""
                INSERT INTO student
                (org_id, name, class_id, roll_no, parent_id, bus_id,
                 assigned_stop_id, rfid_tag, qr_code)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                org_id,
                request.form["name"],
                request.form["class_id"],
                request.form["roll_no"],
                parent_id,
                request.form.get("bus_id") or None,
                request.form.get("assigned_stop_id") or None,
                request.form.get("rfid_tag") or None,
                request.form.get("qr_code") or None
            ))

            student_id = cursor.lastrowid

            if parent_id:
                cursor.execute("""
                    INSERT INTO parent_student (parent_id, student_id)
                    VALUES (%s, %s)
                """, (parent_id, student_id))

            db.commit()
            flash("Student added successfully", "student-success")
            return redirect("/org/students")

        except IntegrityError:
            db.rollback()
            flash("Duplicate Roll No / RFID / QR Code not allowed", "student-danger")

        finally:
            cursor.close()
            db.close()
            
    db, cursor = get_cursor()

    cursor.execute("SELECT id, std, division FROM class_master WHERE org_id=%s", (org_id,))
    classes = cursor.fetchall()

    cursor.execute("SELECT id, name FROM users WHERE org_id=%s AND role='parent'", (org_id,))
    parents = cursor.fetchall()

    cursor.execute("SELECT id, bus_number FROM buses WHERE org_id=%s AND status='ACTIVE'", (org_id,))
    buses = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "org/org_student_add.html",
        classes=classes,
        parents=parents,
        buses=buses
    )


# =========================
# VIEW STUDENT (WITH BUS FEE)
# =========================
@org_bp.route("/students/view/<int:student_id>")
@login_required
def view_student(student_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT
            s.id,
            s.name,
            s.roll_no,
            s.rfid_tag,
            s.qr_code,
            c.std,
            c.division,

            -- Parent
            COALESCE(p1.name, p2.name) AS parent,

            -- Transport
            rs.stop_name,
            rs.monthly_fee AS total_fee,

            b.bus_number,
            r.route_name,
            r.start_time,
            r.drop_time,
            d.name AS driver,

            -- 💰 Fee info (current month)
            IFNULL(f.amount_paid, 0) AS amount_paid,
            IFNULL(rs.monthly_fee, 0) - IFNULL(f.amount_paid, 0) AS remaining_fee

        FROM student s
        JOIN class_master c ON c.id = s.class_id

        LEFT JOIN users p1 
            ON p1.id = s.parent_id AND p1.role='parent'
        LEFT JOIN parent_student ps ON ps.student_id = s.id
        LEFT JOIN users p2 
            ON p2.id = ps.parent_id AND p2.role='parent'

        LEFT JOIN buses b ON b.id = s.bus_id
        LEFT JOIN driver_assignment da
            ON da.id = (
                SELECT MAX(id)
                FROM driver_assignment
                WHERE bus_id = b.id AND status='ASSIGNED'
            )
        LEFT JOIN routes r ON r.id = da.route_id
        LEFT JOIN users d ON d.id = da.driver_id
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id

        LEFT JOIN student_bus_fee f
            ON f.student_id = s.id
            AND f.billing_month = DATE_FORMAT(CURDATE(), '%Y-%m-01')

        WHERE s.id=%s AND s.org_id=%s
        LIMIT 1
    """, (student_id, org_id))

    student = cursor.fetchone()
    cursor.close()
    db.close()

    if not student:
        flash("Student not found", "danger")
        return redirect("/org/students")

    return render_template("org/org_student_view.html", student=student)

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask import Response
import io


# =========================
# DOWNLOAD STUDENT PDF
# =========================
@org_bp.route("/students/pdf/<int:student_id>")
@login_required
def student_pdf(student_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT
            s.name,
            s.roll_no,
            c.std,
            c.division,
            COALESCE(p1.name, p2.name) AS parent,
            rs.stop_name,
            rs.monthly_fee AS total_fee,
            IFNULL(f.amount_paid, 0) AS amount_paid,
            IFNULL(rs.monthly_fee, 0) - IFNULL(f.amount_paid, 0) AS remaining_fee,
            b.bus_number,
            r.route_name,
            TIME_FORMAT(r.start_time, '%H:%i') AS pickup_time,
            TIME_FORMAT(r.drop_time, '%H:%i') AS drop_time,
            d.name AS driver
        FROM student s
        JOIN class_master c ON c.id = s.class_id
        LEFT JOIN users p1 ON p1.id = s.parent_id AND p1.role='parent'
        LEFT JOIN parent_student ps ON ps.student_id = s.id
        LEFT JOIN users p2 ON p2.id = ps.parent_id AND p2.role='parent'
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
        LEFT JOIN buses b ON b.id = s.bus_id
        LEFT JOIN driver_assignment da
            ON da.id = (
                SELECT MAX(id)
                FROM driver_assignment
                WHERE bus_id = b.id AND status='ASSIGNED'
            )
        LEFT JOIN routes r ON r.id = da.route_id
        LEFT JOIN users d ON d.id = da.driver_id
        LEFT JOIN student_bus_fee f
            ON f.student_id = s.id
            AND f.billing_month = DATE_FORMAT(CURDATE(), '%Y-%m-01')
        WHERE s.id=%s AND s.org_id=%s
        LIMIT 1
    """, (student_id, org_id))

    student = cursor.fetchone()
    cursor.close()
    db.close()

    if not student:
        flash("Student not found", "danger")
        return redirect("/org/students")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>Student Transport Details</b>", styles["Title"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    data = [
        ["Name", student["name"]],
        ["Roll No", student["roll_no"]],
        ["Class", f"{student['std']} {student['division']}"],
        ["Parent", student["parent"] or "-"],
        ["Bus", student["bus_number"] or "-"],
        ["Route", student["route_name"] or "-"],
        ["Stop", student["stop_name"] or "-"],
        ["Pickup Time", student["pickup_time"] or "-"],
        ["Drop Time", student["drop_time"] or "-"],
        ["Driver", student["driver"] or "-"],
        ["Monthly Fee", f"₹ {student['total_fee']}"],
        ["Amount Paid", f"₹ {student['amount_paid']}"],
        ["Remaining Fee",
         "Paid" if student["remaining_fee"] <= 0 else f"₹ {student['remaining_fee']} Due"]
    ]

    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 1, colors.grey),
        ("FONT", (0,0), (-1,-1), "Helvetica"),
        ("PADDING", (0,0), (-1,-1), 8),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)

    return Response(
        buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment;filename=student_{student_id}.pdf"
        }
    )



# =========================
# EDIT STUDENT
# =========================
@org_bp.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
@login_required
def edit_student(student_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    # =========================
    # UPDATE STUDENT (POST)
    # =========================
    if request.method == "POST":
        try:
            parent_id = request.form.get("parent_id") or None

            cursor.execute("""
                UPDATE student
                SET name=%s,
                    roll_no=%s,
                    class_id=%s,
                    parent_id=%s,
                    bus_id=%s,
                    assigned_stop_id=%s,
                    rfid_tag=%s,
                    qr_code=%s
                WHERE id=%s AND org_id=%s
            """, (
                request.form["name"],
                request.form["roll_no"],
                request.form["class_id"],
                parent_id,
                request.form.get("bus_id") or None,
                request.form.get("assigned_stop_id") or None,
                request.form.get("rfid_tag") or None,
                request.form.get("qr_code") or None,
                student_id,
                org_id
            ))

            cursor.execute(
                "DELETE FROM parent_student WHERE student_id=%s",
                (student_id,)
            )

            if parent_id:
                cursor.execute("""
                    INSERT INTO parent_student (parent_id, student_id)
                    VALUES (%s, %s)
                """, (parent_id, student_id))

            db.commit()
            flash("Student updated successfully", "student-success")

        except IntegrityError:
            db.rollback()
            flash("Duplicate Roll No / RFID / QR Code not allowed", "danger")

        cursor.close()
        db.close()
        return redirect("/org/students")

    # =========================
    # LOAD STUDENT (GET) + FEE
    # =========================
    cursor.execute("""
        SELECT
            s.id,
            s.name,
            s.roll_no,
            s.class_id,
            s.parent_id,
            s.bus_id,
            s.assigned_stop_id,
            s.rfid_tag,
            s.qr_code,

            -- 💰 Fee info (current month)
            rs.monthly_fee AS total_fee,
            IFNULL(f.amount_paid, 0) AS amount_paid,
            IFNULL(rs.monthly_fee, 0) - IFNULL(f.amount_paid, 0) AS remaining_fee

        FROM student s
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
        LEFT JOIN student_bus_fee f
            ON f.student_id = s.id
            AND f.billing_month = DATE_FORMAT(CURDATE(), '%Y-%m-01')

        WHERE s.id=%s AND s.org_id=%s
    """, (student_id, org_id))

    student = cursor.fetchone()

    if not student:
        cursor.close()
        db.close()
        flash("Student not found", "danger")
        return redirect("/org/students")

    # =========================
    # DROPDOWNS
    # =========================
    cursor.execute(
        "SELECT id, std, division FROM class_master WHERE org_id=%s",
        (org_id,)
    )
    classes = cursor.fetchall()

    cursor.execute(
        "SELECT id, name FROM users WHERE org_id=%s AND role='parent'",
        (org_id,)
    )
    parents = cursor.fetchall()

    cursor.execute(
        "SELECT id, bus_number FROM buses WHERE org_id=%s AND status='ACTIVE'",
        (org_id,)
    )
    buses = cursor.fetchall()

    # =========================
    # STOPS BASED ON BUS
    # =========================
    stops = []
    if student["bus_id"]:
        cursor.execute("""
            SELECT rs.id, rs.stop_name
            FROM route_stop rs
            WHERE rs.route_id = (
                SELECT da.route_id
                FROM driver_assignment da
                WHERE da.bus_id=%s AND da.status='ASSIGNED'
                ORDER BY da.id DESC
                LIMIT 1
            )
            ORDER BY rs.stop_order
        """, (student["bus_id"],))
        stops = cursor.fetchall()
        
    # =========================
    # PAYMENT HISTORY
    # =========================
    cursor.execute("""
        SELECT
            sfp.id,
            sfp.paid_amount,
            sfp.payment_mode,
            sfp.paid_on
        FROM student_fee_payment sfp
        JOIN student_bus_fee sbf ON sbf.id = sfp.fee_id
        WHERE sbf.student_id=%s
        AND sbf.billing_month = DATE_SUB(CURDATE(), INTERVAL DAY(CURDATE())-1 DAY)
        ORDER BY sfp.paid_on DESC
    """, (student_id,))

    payments = cursor.fetchall()
    

    cursor.close()
    db.close()

    return render_template(
        "org/org_student_edit.html",
        student=student,
        classes=classes,
        parents=parents,
        buses=buses,
        stops=stops,
        payments=payments
    )


# =========================
# DELETE STUDENT
# =========================
@org_bp.route("/students/delete/<int:student_id>", methods=["POST"])
@login_required
def delete_student(student_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("DELETE FROM parent_student WHERE student_id=%s", (student_id,))
    cursor.execute("DELETE FROM student WHERE id=%s AND org_id=%s", (student_id, org_id))
    db.commit()

    cursor.close()
    db.close()

    flash("Student deleted successfully", "student-success")
    return redirect("/org/students")


# =========================
# GET BUS DETAILS (AJAX)
# =========================
@org_bp.route("/students/get-bus-details/<int:bus_id>")
@login_required
def get_bus_details(bus_id):
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT
            r.id AS route_id,
            r.route_name,
            r.start_time,
            r.drop_time,
            u.name AS driver_name
        FROM driver_assignment da
        JOIN routes r ON r.id = da.route_id
        JOIN users u ON u.id = da.driver_id
        WHERE da.bus_id=%s AND da.status='ASSIGNED'
        ORDER BY da.id DESC
        LIMIT 1
    """, (bus_id,))

    row = cursor.fetchone()

    if not row:
        cursor.close()
        db.close()
        return jsonify({
            "route_name": "",
            "pickup_time": "",
            "drop_time": "",
            "driver_name": "",
            "stops": []
        })

    cursor.execute("""
        SELECT rs.id, rs.stop_name
        FROM route_stop rs
        WHERE rs.route_id=%s
        ORDER BY rs.stop_order
    """, (row["route_id"],))

    stops = cursor.fetchall()

    cursor.close()
    db.close()

    return jsonify({
        "route_name": row["route_name"],
        "pickup_time": str(row["start_time"]),
        "drop_time": str(row["drop_time"]),
        "driver_name": row["driver_name"],
        "stops": stops
    })


# =========================
# GET STOP FEE (AJAX)
# =========================
@org_bp.route("/students/get-stop-fee/<int:stop_id>")
@login_required
def get_stop_fee(stop_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT monthly_fee
        FROM route_stop
        WHERE id=%s AND org_id=%s
    """, (stop_id, org_id))

    row = cursor.fetchone()
    cursor.close()
    db.close()

    return jsonify({
        "monthly_fee": float(row["monthly_fee"]) if row else 0
    })



# =========================
# PAY STUDENT BUS FEE
# =========================
@org_bp.route("/students/pay-fee/<int:student_id>", methods=["POST"])
@login_required
def pay_student_fee(student_id):
    org_id = session.get("org_id")
    pay_amount = request.form.get("pay_amount")
    payment_mode = request.form.get("payment_mode", "CASH")

    try:
        pay_amount = Decimal(pay_amount)
        if pay_amount <= 0:
            raise ValueError
    except:
        flash("Enter a valid payment amount", "danger")
        return redirect(f"/org/students/edit/{student_id}")

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT id, total_fee, amount_paid
        FROM student_bus_fee
        WHERE student_id=%s
          AND billing_month = DATE_SUB(CURDATE(), INTERVAL DAY(CURDATE())-1 DAY)
    """, (student_id,))
    fee = cursor.fetchone()

    if not fee:
        cursor.execute("""
            SELECT rs.monthly_fee
            FROM route_stop rs
            JOIN student s ON s.assigned_stop_id = rs.id
            WHERE s.id=%s
        """, (student_id,))
        row = cursor.fetchone()
        total_fee = Decimal(row["monthly_fee"]) if row else Decimal(0)

        cursor.execute("""
            INSERT INTO student_bus_fee
            (org_id, student_id, total_fee, amount_paid, billing_month)
            VALUES (%s,%s,%s,0,
                DATE_SUB(CURDATE(), INTERVAL DAY(CURDATE())-1 DAY))
        """, (org_id, student_id, total_fee))

        fee_id = cursor.lastrowid
        amount_paid = Decimal(0)
    else:
        fee_id = fee["id"]
        total_fee = Decimal(fee["total_fee"])
        amount_paid = Decimal(fee["amount_paid"])

    # ✅ SAFE DECIMAL ADDITION
    new_paid = amount_paid + pay_amount

    if new_paid >= total_fee:
        new_paid = total_fee
        status = "PAID"
    else:
        status = "PARTIAL"

    cursor.execute("""
        INSERT INTO student_fee_payment
        (fee_id, paid_amount, payment_mode)
        VALUES (%s,%s,%s)
    """, (fee_id, pay_amount, payment_mode))

    cursor.execute("""
        UPDATE student_bus_fee
        SET amount_paid=%s, status=%s
        WHERE id=%s
    """, (new_paid, status, fee_id))

    db.commit()
    cursor.close()
    db.close()

    flash("Fee payment recorded successfully", "success")
    return redirect(f"/org/students/edit/{student_id}")

# =========================
# DOWNLOAD PAYMENT RECEIPT (PDF)
# =========================
@org_bp.route("/students/payment-receipt/<int:payment_id>")
@login_required
def payment_receipt_pdf(payment_id):
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT
            s.name AS student_name,
            s.roll_no,
            c.std,
            c.division,

            rs.stop_name,
            rs.monthly_fee,

            sbf.billing_month,
            sbf.total_fee,
            sbf.amount_paid,
            (sbf.total_fee - sbf.amount_paid) AS remaining_fee,
            sbf.status,

            sfp.paid_amount,
            sfp.payment_mode,
            sfp.paid_on,

            b.bus_number

        FROM student_fee_payment sfp
        JOIN student_bus_fee sbf ON sbf.id = sfp.fee_id
        JOIN student s ON s.id = sbf.student_id
        JOIN class_master c ON c.id = s.class_id
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
        LEFT JOIN buses b ON b.id = s.bus_id

        WHERE sfp.id=%s AND sbf.org_id=%s
        LIMIT 1
    """, (payment_id, org_id))

    data = cursor.fetchone()
    cursor.close()
    db.close()

    if not data:
        flash("Payment not found", "danger")
        return redirect("/org/students")

    # =========================
    # CREATE PDF
    # =========================
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>Bus Fee Payment Receipt</b>", styles["Title"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    table_data = [
        ["Student Name", data["student_name"]],
        ["Roll No", data["roll_no"]],
        ["Class", f"{data['std']} {data['division']}"],
        ["Bus Number", data["bus_number"] or "-"],
        ["Stop", data["stop_name"] or "-"],
        ["Billing Month", data["billing_month"].strftime("%B %Y")],

        ["Total Monthly Fee", f"₹ {data['total_fee']}"],
        ["Paid Amount", f"₹ {data['paid_amount']}"],

        ["Remaining Fee",
        "₹ 0.00" if data["remaining_fee"] <= 0
        else f"₹ {data['remaining_fee']}"],

        ["Payment Mode", data["payment_mode"]],
        ["Payment Date", data["paid_on"].strftime("%d-%m-%Y %I:%M %p")],
        ["Status", data["status"]],
    ]

    table = Table(table_data, colWidths=[160, 300])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONT", (0,0), (-1,-1), "Helvetica"),
        ("PADDING", (0,0), (-1,-1), 8),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    return Response(
        buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            f"attachment; filename=Receipt_{payment_id}.pdf"
        }
    )

# =========================
# DOWNLOAD STUDENT LIST PDF (ALL / CLASS WISE)
# =========================
@org_bp.route("/students/pdf")
@login_required
def students_list_pdf():
    org_id = session.get("org_id")
    class_id = request.args.get("class_id")

    db, cursor = get_cursor()

    query = """
        SELECT
            s.name,
            s.roll_no,
            c.std,
            c.division,
            rs.stop_name,
            b.bus_number,
            rs.monthly_fee AS total_fee,
            IFNULL(f.amount_paid, 0) AS amount_paid,
            IFNULL(rs.monthly_fee, 0) - IFNULL(f.amount_paid, 0) AS remaining_fee
        FROM student s
        JOIN class_master c ON c.id = s.class_id
        LEFT JOIN route_stop rs ON rs.id = s.assigned_stop_id
        LEFT JOIN buses b ON b.id = s.bus_id
        LEFT JOIN student_bus_fee f
            ON f.student_id = s.id
            AND f.billing_month = DATE_SUB(CURDATE(), INTERVAL DAY(CURDATE())-1 DAY)
        WHERE s.org_id=%s
    """

    params = [org_id]

    if class_id:
        query += " AND s.class_id=%s"
        params.append(class_id)

    query += " ORDER BY c.std, c.division, s.roll_no"

    cursor.execute(query, tuple(params))
    students = cursor.fetchall()

    # =========================
    # FETCH CLASS NAME (BEFORE CLOSE)
    # =========================
    class_name = None
    if class_id:
        cursor.execute("""
            SELECT std, division
            FROM class_master
            WHERE id=%s AND org_id=%s
        """, (class_id, org_id))

        cls = cursor.fetchone()
        if cls:
            class_name = f"{cls['std']} {cls['division']}"

    cursor.close()
    db.close()

    # ================= PDF =================
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # ================= TITLE =================
    if class_name:
        title = f"Student Transport List – Class {class_name}"
    else:
        title = "Student Transport List (All Classes)"

    elements.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    # ================= TABLE =================
    table_data = [[
        "Name", "Class", "Roll", "Bus", "Stop",
        "Fee", "Paid", "Due"
    ]]

    for s in students:
        table_data.append([
            s["name"],
            f"{s['std']} {s['division']}",
            s["roll_no"],
            s["bus_number"] or "-",
            s["stop_name"] or "-",
            f"₹ {s['total_fee'] or 0}",
            f"₹ {s['amount_paid'] or 0}",
            "Paid" if (s["remaining_fee"] or 0) <= 0 else f"₹ {s['remaining_fee']}"
        ])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (5,1), (-1,-1), "RIGHT"),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    filename = "students_list.pdf" if not class_id else "students_class_list.pdf"

    return Response(
        buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
