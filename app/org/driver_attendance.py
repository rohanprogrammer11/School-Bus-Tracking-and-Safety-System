from flask import (
    render_template, request, session,
    redirect, url_for, send_file
)
from datetime import date, datetime
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp

import calendar
import pandas as pd
from io import BytesIO

from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime, date


# =====================================================
# HELPER: MONTHLY ATTENDANCE + SALARY (WITH OT)
# =====================================================
def get_monthly_attendance_summary(cursor, org_id, year, month):

    total_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, total_days)

    cursor.execute("""
        SELECT
            u.id AS driver_id,
            u.name,
            d.driver_code,
            d.monthly_salary,
            da.status
        FROM users u
        JOIN driver_details d ON d.driver_id = u.id
        LEFT JOIN driver_attendance da
            ON da.driver_id = u.id
           AND da.date BETWEEN %s AND %s
        WHERE u.org_id = %s
          AND u.role = 'driver'
          AND u.is_active = 1
        ORDER BY u.name
    """, (start_date, end_date, org_id))

    data = {}

    for r in cursor.fetchall():
        driver_id = r["driver_id"]

        data.setdefault(driver_id, {
            "id": driver_id,
            "name": r["name"],
            "code": r["driver_code"],
            "monthly_salary": r["monthly_salary"],
            "present": 0,
            "leave": 0,
            "overtime": 0
        })

        if r["status"] == "PRESENT":
            data[driver_id]["present"] += 1
        elif r["status"] == "OVERTIME":
            data[driver_id]["overtime"] += 1
        elif r["status"] == "LEAVE":
            data[driver_id]["leave"] += 1

    rows = []

    for d in data.values():
        per_day = d["monthly_salary"] / total_days if total_days else 0
        paid_days = d["present"] + d["overtime"]
        absent = total_days - d["present"] - d["leave"] - d["overtime"]

        ot_salary = round(d["overtime"] * per_day, 2)
        salary = round(paid_days * per_day, 2)

        rows.append((
            d["id"],
            d["name"],
            d["code"],
            d["monthly_salary"],
            total_days,
            d["present"],
            d["leave"],
            absent,
            d["overtime"],
            ot_salary,
            salary
        ))

    return rows

#-------------------------
#------------------------
def get_monthly_attendance_calendar(cursor, org_id, year, month):
    start_date = date(year, month, 1)
    total_days = calendar.monthrange(year, month)[1]
    end_date = date(year, month, total_days)

    cursor.execute("""
        SELECT
            u.id,
            u.name,
            d.driver_code,
            da.date,
            COALESCE(da.status,'ABSENT')
        FROM users u
        JOIN driver_details d ON d.driver_id = u.id
        LEFT JOIN driver_attendance da
            ON da.driver_id = u.id
           AND da.date BETWEEN %s AND %s
        WHERE u.org_id=%s
          AND u.role='driver'
          AND u.is_active=1
        ORDER BY u.name, da.date
    """, (start_date, end_date, org_id))

    return cursor.fetchall(), total_days

# =====================================================
# REGISTER BUILDER (WITH OT + SALARY)
# =====================================================
def build_register(cursor, org_id, year, month):

    total_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, total_days)

    # ---------------- DRIVERS ----------------
    cursor.execute("""
        SELECT
            u.id            AS driver_id,
            u.name          AS name,
            d.driver_code   AS code,
            d.monthly_salary,
            d.overtime_rate
        FROM users u
        JOIN driver_details d ON d.driver_id = u.id
        WHERE u.org_id=%s
          AND u.role='driver'
          AND u.is_active=1
        ORDER BY u.name
    """, (org_id,))
    drivers = cursor.fetchall()

    # ---------------- ATTENDANCE ----------------
    cursor.execute("""
        SELECT driver_id, date, status
        FROM driver_attendance
        WHERE org_id=%s
          AND date BETWEEN %s AND %s
    """, (org_id, start_date, end_date))
    attendance = cursor.fetchall()

    # ---------------- HOLIDAYS ----------------
    cursor.execute("""
        SELECT holiday_date
        FROM public_holidays
        WHERE org_id=%s
          AND holiday_date BETWEEN %s AND %s
    """, (org_id, start_date, end_date))
    holidays = {r["holiday_date"] for r in cursor.fetchall()}

    # ---------------- BUILD REGISTER ----------------
    register = {}

    for d in drivers:
        driver_id = d["driver_id"]

        register[driver_id] = {
            "name": d["name"],
            "code": d["code"],
            "monthly_salary": d["monthly_salary"] or 0,
            "ot_rate": d["overtime_rate"] or 0,
            "days": {},
            "present": 0,
            "leave": 0,
            "absent": 0,
            "overtime": 0,
            "salary": 0
        }

        for day in range(1, total_days + 1):
            dt = date(year, month, day)
            register[driver_id]["days"][day] = (
                "H" if dt.weekday() == 6 or dt in holidays else "A"
            )

    # ---------------- APPLY ATTENDANCE ----------------
    for a in attendance:
        driver_id = a["driver_id"]
        att_date = a["date"]
        status = a["status"]

        if driver_id not in register:
            continue

        day = att_date.day

        if status == "PRESENT":
            register[driver_id]["days"][day] = "P"
        elif status == "LEAVE":
            register[driver_id]["days"][day] = "L"
        elif status == "OVERTIME":
            register[driver_id]["days"][day] = "OT"
        elif status == "HOLIDAY":
            register[driver_id]["days"][day] = "H"

    # ---------------- SALARY ----------------
    for d in register.values():
        p  = sum(v == "P" for v in d["days"].values())
        l  = sum(v == "L" for v in d["days"].values())
        ot = sum(v == "OT" for v in d["days"].values())

        per_day = d["monthly_salary"] / total_days if total_days else 0
        base_salary = per_day * (p + ot)
        ot_salary   = ot * d["ot_rate"]

        d["present"]  = p
        d["leave"]    = l
        d["absent"]   = total_days - p - l
        d["overtime"] = ot
        d["salary"]   = round(base_salary + ot_salary, 2)

    return register, total_days


@org_bp.route("/driver-attendance")
@login_required
def driver_attendance_dashboard():

    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]
    selected_date = date.fromisoformat(
        request.args.get("date") or date.today().isoformat()
    )

    year = selected_date.year
    month = selected_date.month
    total_days = calendar.monthrange(year, month)[1]

    month_start = date(year, month, 1)
    month_end = date(year, month, total_days)

    db, cursor = get_cursor()

    # ---------------- SUMMARY (TODAY) ----------------
    cursor.execute("""
        SELECT
            SUM(CASE WHEN da.status='PRESENT' THEN 1 ELSE 0 END) AS present,
            SUM(CASE WHEN da.status='ABSENT' THEN 1 ELSE 0 END) AS absent,
            SUM(CASE WHEN da.status='LEAVE' THEN 1 ELSE 0 END) AS leave_days
        FROM users u
        LEFT JOIN driver_attendance da
            ON da.driver_id=u.id AND da.date=%s
        WHERE u.org_id=%s
          AND u.role='driver'
          AND u.is_active=1
    """, (selected_date, org_id))

    stats = cursor.fetchone()
    present = stats["present"] or 0
    absent = stats["absent"] or 0
    leave = stats["leave_days"] or 0

    # ---------------- DRIVER LIST (MONTHLY + TODAY) ----------------
    cursor.execute("""
        SELECT
            u.id,
            u.name,
            d.driver_code,
            d.monthly_salary,
            d.overtime_rate,

            -- Today
            da_today.check_in,
            da_today.check_out,
            COALESCE(da_today.status,'ABSENT') AS today_status,

            -- Monthly counts
            SUM(CASE WHEN da.status='PRESENT' THEN 1 ELSE 0 END) AS present_days,
            SUM(CASE WHEN da.status='OVERTIME' THEN 1 ELSE 0 END) AS ot_days

        FROM users u
        JOIN driver_details d ON d.driver_id=u.id

        LEFT JOIN driver_attendance da
            ON da.driver_id=u.id
           AND da.date BETWEEN %s AND %s

        LEFT JOIN driver_attendance da_today
            ON da_today.driver_id=u.id
           AND da_today.date=%s

        WHERE u.org_id=%s
          AND u.role='driver'
          AND u.is_active=1

        GROUP BY u.id
        ORDER BY u.name
    """, (month_start, month_end, selected_date, org_id))

    drivers = []

    for r in cursor.fetchall():
        monthly_salary = r["monthly_salary"] or 0
        ot_rate = r["overtime_rate"] or 0

        present_days = r["present_days"] or 0
        ot_days = r["ot_days"] or 0

        per_day = monthly_salary / total_days if total_days else 0

        base_salary = round((present_days + ot_days) * per_day, 2)
        ot_salary = round(ot_days * per_day, 2)   # 🔥 OT AS PAID DAY

        total_salary = round(base_salary, 2)

        drivers.append({
            "id": r["id"],
            "name": r["name"],
            "driver_code": r["driver_code"],
            "check_in": r["check_in"],
            "check_out": r["check_out"],
            "status": r["today_status"],
            "monthly_salary": monthly_salary,
            "present_days": present_days,
            "ot_days": ot_days,
            "ot_salary": ot_salary,
            "total_salary": total_salary
        })

    cursor.close()
    db.close()

    return render_template(
        "org/driver_attendance_dashboard.html",
        drivers=drivers,
        selected_date=selected_date,
        present=present,
        absent=absent,
        leave=leave
    )


# =====================================================
# CHECK OUT
# =====================================================
@org_bp.route("/driver-attendance/check-out", methods=["POST"])
@login_required
def driver_check_out():

    if session.get("role") != "admin":
        return "Unauthorized", 403

    driver_id = request.form["driver_id"]
    att_date = request.form["date"]

    db, cursor = get_cursor()
    cursor.execute("""
        UPDATE driver_attendance
        SET check_out=%s
        WHERE driver_id=%s AND date=%s
    """, (datetime.now(), driver_id, att_date))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for("org.driver_attendance_dashboard", date=att_date))



# =====================================================
# MARK ATTENDANCE
# =====================================================
@org_bp.route("/driver-attendance/mark/<status>", methods=["POST"])
@login_required
def mark_driver_attendance(status):

    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]
    driver_id = request.form["driver_id"]
    att_date = request.form["date"]

    status = status.upper()

    check_in_time = None
    check_out_time = None

    # ✅ Only PRESENT sets check-in
    if status == "PRESENT":
        check_in_time = datetime.now()

    db, cursor = get_cursor()

    cursor.execute("""
        INSERT INTO driver_attendance (
            org_id, driver_id, date,
            status, check_in, check_out
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            status=%s,
            check_in=%s,
            check_out=%s
    """, (
        org_id, driver_id, att_date,
        status, check_in_time, check_out_time,
        status, check_in_time, check_out_time
    ))

    db.commit()
    cursor.close()
    db.close()

    return redirect(
        url_for("org.driver_attendance_dashboard", date=att_date)
    )

# =====================================================
# MONTHLY EXCEL
# =====================================================
@org_bp.route("/driver-attendance/report/excel")
@login_required
def attendance_excel():

    year = int(request.args["year"])
    month = int(request.args["month"])
    org_id = session["org_id"]

    db, cursor = get_cursor()
    data = get_monthly_attendance_summary(cursor, org_id, year, month)
    cursor.close()
    db.close()

    df = pd.DataFrame(data, columns=[
        "Driver ID","Driver Name","Driver Code",
        "Monthly Salary","Total Days",
        "Present Days","Leave Days","Absent Days",
        "OT Days","OT Salary","Payable Salary"
    ])

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Driver_Salary_{calendar.month_name[month]}_{year}.xlsx"
    )

# =====================================================
# MONTHLY PDF
# =====================================================
@org_bp.route("/driver-attendance/report/pdf")
@login_required
def attendance_pdf():

    year = int(request.args["year"])
    month = int(request.args["month"])
    org_id = session["org_id"]

    db, cursor = get_cursor()
    data = get_monthly_attendance_summary(cursor, org_id, year, month)
    cursor.close()
    db.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(
        Paragraph(
            f"<b>Driver Salary Report – {calendar.month_name[month]} {year}</b>",
            styles["Title"]
        )
    )
    elements.append(Spacer(1, 15))

    table_data = [[
        "ID","Driver","Code","Monthly",
        "Days","Present","Leave","Absent",
        "OT","OT Salary","Salary"
    ]]

    for r in data:
        table_data.append(list(r))

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.5,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
        ("FONT",(0,0),(-1,0),"Helvetica-Bold")
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Driver_Salary_{calendar.month_name[month]}_{year}.pdf",
        mimetype="application/pdf"
    )    
    
#-------------------------------
#------------------------------
@org_bp.route("/driver-attendance/register")
@login_required
def driver_attendance_register():

    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]
    year = int(request.args.get("year", date.today().year))
    month = int(request.args.get("month", date.today().month))

    total_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, total_days)

    db, cursor = get_cursor()

    # =====================================================
    # 1️⃣ FETCH DRIVERS (ONCE — NO DUPLICATES)
    # =====================================================
    cursor.execute("""
        SELECT
            u.id            AS driver_id,
            u.name          AS driver_name,
            d.driver_code   AS driver_code,
            d.monthly_salary,
            d.overtime_rate
        FROM users u
        JOIN driver_details d ON d.driver_id = u.id
        WHERE u.org_id=%s
          AND u.role='driver'
          AND u.is_active=1
        ORDER BY u.name
    """, (org_id,))

    drivers = cursor.fetchall()

    # =====================================================
    # 2️⃣ FETCH ATTENDANCE
    # =====================================================
    cursor.execute("""
        SELECT
            driver_id,
            date,
            status
        FROM driver_attendance
        WHERE org_id=%s
          AND date BETWEEN %s AND %s
    """, (org_id, start_date, end_date))

    attendance_rows = cursor.fetchall()

    # =====================================================
    # 3️⃣ FETCH HOLIDAYS
    # =====================================================
    cursor.execute("""
        SELECT holiday_date
        FROM public_holidays
        WHERE org_id=%s
          AND holiday_date BETWEEN %s AND %s
    """, (org_id, start_date, end_date))

    holiday_dates = {r[0] for r in cursor.fetchall()}

    cursor.close()
    db.close()

    # =====================================================
    # 4️⃣ BUILD REGISTER (CLEAN & SAFE)
    # =====================================================
    register = {}

    for d in drivers:
        driver_id = d["driver_id"]

        register[driver_id] = {
            "name": d["driver_name"],
            "code": d["driver_code"],
            "monthly_salary": d["monthly_salary"] or 0,
            "ot_rate": d["overtime_rate"] or 0,
            "days": {},
            "present": 0,
            "absent": 0,
            "leave": 0,
            "overtime": 0,
            "salary": 0
        }

        # Auto-fill days
        for day in range(1, total_days + 1):
            current_date = date(year, month, day)
            if current_date.weekday() == 6 or current_date in holiday_dates:
                register[driver_id]["days"][day] = "H"
            else:
                register[driver_id]["days"][day] = "A"

    # =====================================================
    # 5️⃣ APPLY ATTENDANCE
    # =====================================================
    for r in attendance_rows:
        driver_id = r["driver_id"]
        att_date = r["date"]
        status = r["status"]

        if driver_id not in register:
            continue

        day = att_date.day

        if status == "PRESENT":
            register[driver_id]["days"][day] = "P"
        elif status == "LEAVE":
            register[driver_id]["days"][day] = "L"
        elif status == "OVERTIME":
            register[driver_id]["days"][day] = "OT"
        elif status == "HOLIDAY":
            register[driver_id]["days"][day] = "H"
        else:
            register[driver_id]["days"][day] = "A"

    # =====================================================
    # 6️⃣ CALCULATE TOTALS & SALARY
    # =====================================================
    for d in register.values():
        present = sum(v == "P" for v in d["days"].values())
        leave   = sum(v == "L" for v in d["days"].values())
        ot      = sum(v == "OT" for v in d["days"].values())

        per_day = d["monthly_salary"] / total_days if total_days else 0

        base_salary = per_day * (present + ot)
        ot_salary   = ot * d["ot_rate"]

        d["present"]  = present
        d["leave"]    = leave
        d["absent"]   = total_days - present - leave
        d["overtime"] = ot
        d["salary"]   = round(base_salary + ot_salary, 2)

    # =====================================================
    # 7️⃣ RENDER
    # =====================================================
    return render_template(
        "org/driver_attendance_register.html",
        register=register,
        total_days=total_days,
        month=month,
        year=year,
        month_name=calendar.month_name[month]
    )


#------------------
# register excel
#-----------------
@org_bp.route("/driver-attendance/register/excel")
@login_required
def register_excel():

    org_id = session["org_id"]
    year = int(request.args["year"])
    month = int(request.args["month"])

    db, cursor = get_cursor()
    register, total_days = build_register(cursor, org_id, year, month)
    cursor.close()
    db.close()

    rows = []
    for d in register.values():
        row = [d["name"], d["code"]]
        for day in range(1, total_days + 1):
            row.append(d["days"][day])
        row += [d["present"], d["absent"], d["leave"], d["overtime"], d["salary"]]
        rows.append(row)

    columns = (
        ["Driver", "Code"] +
        [str(i) for i in range(1, total_days + 1)] +
        ["P", "A", "L", "OT", "Salary"]
    )

    df = pd.DataFrame(rows, columns=columns)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name=f"Attendance_Register_{calendar.month_name[month]}_{year}.xlsx",
        as_attachment=True
    )


# =====================================================
# REGISTER PDF (FIXED LAYOUT + OT COLUMN)
# =====================================================
@org_bp.route("/driver-attendance/register/pdf")
@login_required
def register_pdf():

    org_id = session["org_id"]
    year = int(request.args["year"])
    month = int(request.args["month"])

    db, cursor = get_cursor()
    register, total_days = build_register(cursor, org_id, year, month)
    cursor.close()
    db.close()

    buffer = BytesIO()
    page_width, _ = landscape(A4)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15,
        rightMargin=15,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(
        Paragraph(
            f"<b>Attendance Register – {calendar.month_name[month]} {year}</b>",
            styles["Title"]
        )
    )
    elements.append(Spacer(1, 10))

    header = ["Driver", "Code"] \
        + [str(i) for i in range(1, total_days + 1)] \
        + ["P", "A", "L", "OT", "Salary"]

    col_widths = (
        [95, 35] +
        [14] * total_days +
        [26, 26, 26, 28, 65]
    )

    table_data = [header]

    for d in register.values():
        row = [d["name"], d["code"]]
        row += [d["days"][i] for i in range(1, total_days + 1)]
        row += [
            d["present"],
            d["absent"],
            d["leave"],
            d["overtime"],
            f"₹{d['salary']:.2f}"
        ]
        table_data.append(row)

    table = Table(
        table_data,
        colWidths=col_widths,
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.6, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 8),

        ("FONTSIZE", (0,1), (-1,-1), 7),
        ("ALIGN", (2,1), (-5,-1), "CENTER"),
        ("ALIGN", (-4,1), (-1,-1), "CENTER"),

        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),

        ("LINEBEFORE", (-4,0), (-4,-1), 1.2, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Attendance_Register_{calendar.month_name[month]}_{year}.pdf",
        mimetype="application/pdf"
    )
    
    
#-----------------
#-----------------
@org_bp.route("/driver-attendance/register/update", methods=["POST"])
@login_required
def update_register():

    if session.get("role") != "admin":
        return "Unauthorized", 403

    org_id = session["org_id"]

    year = int(request.args.get("year", date.today().year))
    month = int(request.args.get("month", date.today().month))

    db, cursor = get_cursor()

    # Fetch holidays
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])

    cursor.execute("""
        SELECT holiday_date
        FROM public_holidays
        WHERE org_id=%s
          AND holiday_date BETWEEN %s AND %s
    """, (org_id, start_date, end_date))

    holidays = {r[0] for r in cursor.fetchall()}

    for key, ui_status in request.form.items():

        if not key.startswith("attendance["):
            continue

        parts = key.replace("attendance[", "").replace("]", "").split("[")
        driver_code = parts[0]
        day = int(parts[1])

        att_date = date(year, month, day)

        cursor.execute(
            "SELECT driver_id FROM driver_details WHERE driver_code=%s",
            (driver_code,)
        )
        row = cursor.fetchone()
        if not row:
            continue

        driver_id = row[0]

        # UI → DB mapping
        if ui_status == "OT":
            db_status = "OVERTIME"
        elif ui_status == "P":
            db_status = "PRESENT"
        elif ui_status == "A":
            db_status = "ABSENT"
        elif ui_status == "L":
            db_status = "LEAVE"
        elif ui_status == "H":
            db_status = "HOLIDAY"
        else:
            continue

        cursor.execute("""
            INSERT INTO driver_attendance (org_id, driver_id, date, status)
            VALUES (%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE status=%s
        """, (org_id, driver_id, att_date, db_status, db_status))

    db.commit()
    cursor.close()
    db.close()

    return redirect(
        url_for("org.driver_attendance_register",
                month=month, year=year)
    )
