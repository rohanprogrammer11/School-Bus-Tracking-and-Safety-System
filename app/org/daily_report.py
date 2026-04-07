from datetime import date, datetime
from flask import render_template, request, session, jsonify
from app.extensions import get_cursor
from app.org.blueprint import org_bp
from app.driver.blueprint import driver_bp


# =====================================================
# 📊 DAILY REPORT PAGE (ORG)
# =====================================================
@org_bp.route("/daily-reports")
def daily_report_home():
    db, cursor = get_cursor()

    org_id = session.get("org_id", 1)

    # ✅ FIX DATE
    report_date = request.args.get("date")
    if report_date:
        report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    else:
        report_date = date.today()

    # =============================
    # 🚌 BUS REPORT
    # =============================
    cursor.execute("""
        SELECT
            b.bus_number,
            u.name AS driver_name,
            r.route_name,
            d.total_distance_km,
            d.fuel_used,
            d.fuel_cost,
            d.total_trips
        FROM daily_bus_operation_report d
        JOIN buses b ON b.id = d.bus_id
        JOIN users u ON u.id = d.driver_id
        JOIN routes r ON r.id = d.route_id
        WHERE d.org_id = %s
        AND d.report_date = %s
        ORDER BY b.bus_number
    """, (org_id, report_date))

    bus_reports = cursor.fetchall()

    # =============================
    # 👨‍✈️ DRIVER REPORT
    # =============================
    cursor.execute("""
        SELECT
            u.name AS driver_name,
            b.bus_number,
            r.route_name,
            d.total_distance_km,
            d.total_trips
        FROM daily_bus_operation_report d
        JOIN users u ON u.id = d.driver_id
        JOIN buses b ON b.id = d.bus_id
        JOIN routes r ON r.id = d.route_id
        WHERE d.org_id = %s
        AND d.report_date = %s
        ORDER BY u.name
    """, (org_id, report_date))

    driver_reports = cursor.fetchall()

    print("📊 TODAY REPORT:", bus_reports)

    cursor.close()
    db.close()

    return render_template(
        "org/daily_reports.html",
        bus_reports=bus_reports,
        driver_reports=driver_reports,
        report_date=report_date
    )


# =====================================================
# 🔄 UPDATE DAILY REPORT (REAL-TIME)
# =====================================================
def update_daily_report(trip_id):
    db, cursor = get_cursor()

    # =============================
    # GET BASIC TRIP DATA
    # =============================
    cursor.execute("""
        SELECT 
            bt.trip_date,
            bt.bus_id,
            bt.route_id,
            da.driver_id,
            da.assignment
        FROM bus_trip bt
        JOIN driver_assignment da ON da.id = bt.assignment_id
        WHERE bt.id = %s
    """, (trip_id,))
    
    trip = cursor.fetchone()
    if not trip:
        return

    # =============================
    # GET ORG ID
    # =============================
    cursor.execute("SELECT org_id FROM buses WHERE id=%s", (trip["bus_id"],))
    org_id = cursor.fetchone()["org_id"]

    # =============================
    # 🔥 CALCULATE TOTALS (CORRECT WAY)
    # =============================
    cursor.execute("""
        SELECT 
            SUM(distance_km) AS total_km,
            COUNT(*) AS total_trips
        FROM bus_trip
        WHERE bus_id=%s
          AND route_id=%s
          AND DATE(trip_date)=%s
          AND status='COMPLETED'
    """, (trip["bus_id"], trip["route_id"], trip["trip_date"]))

    trip_totals = cursor.fetchone()

    # =============================
    # 🔥 FUEL TOTAL FROM TABLE
    # =============================
    cursor.execute("""
        SELECT 
            SUM(fuel_used) AS fuel_used,
            SUM(fuel_cost) AS fuel_cost
        FROM fuel_consumption
        WHERE bus_id=%s
          AND trip_date=%s
    """, (trip["bus_id"], trip["trip_date"]))

    fuel_totals = cursor.fetchone()

    # =============================
    # INSERT OR UPDATE
    # =============================
    cursor.execute("""
        INSERT INTO daily_bus_operation_report (
            org_id, report_date, bus_id, driver_id, route_id,
            assignment_type, total_distance_km, total_trips,
            fuel_used, fuel_cost
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)

        ON DUPLICATE KEY UPDATE
            total_distance_km = VALUES(total_distance_km),
            total_trips = VALUES(total_trips),
            fuel_used = VALUES(fuel_used),
            fuel_cost = VALUES(fuel_cost),
            last_trip_end = NOW()
    """, (
        org_id,
        trip["trip_date"],
        trip["bus_id"],
        trip["driver_id"],
        trip["route_id"],
        trip["assignment"],
        trip_totals["total_km"] or 0,
        trip_totals["total_trips"] or 0,
        fuel_totals["fuel_used"] or 0,
        fuel_totals["fuel_cost"] or 0
    ))

    db.commit()
    cursor.close()
    db.close()
        

# =====================================================
# 🚍 COMPLETE TRIP API (DRIVER)
# =====================================================
@driver_bp.route("/complete-trip", methods=["POST"])
def complete_trip():
    print("🚀 COMPLETE TRIP API CALLED")

    # ✅ GET DATA FROM JSON OR FORM
    data = request.get_json(silent=True)

    trip_id = None
    if data:
        trip_id = data.get("trip_id")

    if not trip_id:
        trip_id = request.form.get("trip_id")

    print("🔥 RECEIVED TRIP ID:", trip_id)

    if not trip_id:
        return jsonify({"error": "Trip ID missing"}), 400

    db, cursor = get_cursor()

    # =============================
    # MARK TRIP COMPLETED
    # =============================
    cursor.execute("""
        UPDATE bus_trip
        SET status='COMPLETED', end_time=NOW()
        WHERE id=%s
    """, (trip_id,))
    
    db.commit()

    cursor.close()
    db.close()

    print("✅ TRIP COMPLETED")

    # =============================
    # 🔥 UPDATE REPORT
    # =============================
    update_daily_report(trip_id)

    return jsonify({"status": "success"})


@org_bp.route("/api/daily-report")
def api_daily_report():
    db, cursor = get_cursor()
    org_id = session.get("org_id")

    cursor.execute("""
        SELECT b.bus_number, u.name AS driver_name,
               r.route_name, d.total_distance_km, d.total_trips
        FROM daily_bus_operation_report d
        JOIN buses b ON b.id = d.bus_id
        JOIN users u ON u.id = d.driver_id
        JOIN routes r ON r.id = d.route_id
        WHERE d.org_id=%s AND d.report_date=CURDATE()
    """, (org_id,))

    data = cursor.fetchall()
    return jsonify(data)



from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from flask import send_file, request, session
from app.extensions import get_cursor
from app.org.blueprint import org_bp


# =====================================================
# 📥 DOWNLOAD PDF REPORT (FULL DYNAMIC)
# =====================================================
@org_bp.route("/download-report")
def download_report():

    org_id = session.get("org_id")

    report_type = request.args.get("type")   # month / year
    month = request.args.get("month")        # YYYY-MM
    year = request.args.get("year")          # YYYY
    bus_id = request.args.get("bus_id")
    driver_id = request.args.get("driver_id")

    db, cursor = get_cursor()

    # =========================
    # BASE QUERY
    # =========================
    query = """
        SELECT 
            b.bus_number,
            u.name AS driver_name,
            r.route_name,
            d.total_distance_km,
            d.total_trips,
            d.report_date
        FROM daily_bus_operation_report d
        JOIN buses b ON b.id = d.bus_id
        JOIN users u ON u.id = d.driver_id
        JOIN routes r ON r.id = d.route_id
        WHERE d.org_id = %s
    """

    params = [org_id]

    # =========================
    # FILTERS
    # =========================
    if report_type == "month" and month:
        query += " AND DATE_FORMAT(d.report_date, '%Y-%m') = %s"
        params.append(month)

    if report_type == "year" and year:
        query += " AND YEAR(d.report_date) = %s"
        params.append(year)

    if bus_id:
        query += " AND d.bus_id = %s"
        params.append(bus_id)

    if driver_id:
        query += " AND d.driver_id = %s"
        params.append(driver_id)

    query += " ORDER BY d.report_date DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    cursor.close()
    db.close()

    # =========================
    # PDF GENERATION
    # =========================
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    # 🔥 Dynamic Title
    title = "School Bus Transport Report"

    if report_type == "month":
        title += f" (Month: {month})"
    elif report_type == "year":
        title += f" (Year: {year})"

    if bus_id:
        title += f" | Bus ID: {bus_id}"

    if driver_id:
        title += f" | Driver ID: {driver_id}"

    elements.append(Paragraph(title, styles["Title"]))

    # =========================
    # TABLE DATA
    # =========================
    data = [["Date", "Bus", "Driver", "Route", "KM", "Trips"]]

    total_km = 0
    total_trips = 0

    for r in rows:
        total_km += float(r["total_distance_km"] or 0)
        total_trips += int(r["total_trips"] or 0)

        data.append([
            str(r["report_date"]),
            r["bus_number"],
            r["driver_name"],
            r["route_name"],
            str(r["total_distance_km"]),
            str(r["total_trips"])
        ])

    # ✅ Add Summary Row
    data.append([
        "TOTAL",
        "-",
        "-",
        "-",
        str(total_km),
        str(total_trips)
    ])

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.darkblue),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),  # total row
        ("ALIGN",(4,1),(-1,-1),"CENTER")
    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="transport_report.pdf",
        mimetype="application/pdf"
    )