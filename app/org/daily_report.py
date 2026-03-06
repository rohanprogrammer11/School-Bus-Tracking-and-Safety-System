from datetime import date
from flask import render_template, request, session
from app.extensions import get_cursor
from app.org.blueprint import org_bp   # ✅ USE EXISTING ORG BLUEPRINT


# =====================================================
# 📊 DAILY REPORT (TABLE VIEW)
# URL: /org/reports
# =====================================================
@org_bp.route("/daily-reports")
def daily_report_home():
    db, cursor = get_cursor()

    org_id = session.get("org_id", 1)
    report_date = request.args.get("date", date.today())

    # =============================
    # BUS-WISE DAILY REPORT
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
    # DRIVER-WISE DAILY REPORT
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

    cursor.close()
    db.close()

    return render_template(
        "org/daily_reports.html",
        bus_reports=bus_reports,
        driver_reports=driver_reports,
        report_date=report_date
    )
