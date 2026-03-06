from flask import render_template, request, session
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
from datetime import date
import calendar
from flask import Response
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io



@org_bp.route("/reports/fuel-monthly")
@login_required
def monthly_fuel_report():

    month = request.args.get("month")
    year = request.args.get("year")

    # Default: current month
    today = date.today()
    month = int(month) if month else today.month
    year = int(year) if year else today.year

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    db, cursor = get_cursor()
    try:
        cursor.execute("""
            SELECT
                b.bus_number,
                b.fuel_type,

                COUNT(DISTINCT bt.id) AS total_trips,
                COALESCE(SUM(bt.distance_km),0) AS total_distance_km,

                /* Fuel used = distance / mileage */
                ROUND(
                    COALESCE(SUM(bt.distance_km),0) / NULLIF(b.mileage_kmpl, 0),
                    2
                ) AS total_fuel_used,

                /* Fuel cost = fuel_used * price */
                ROUND(
                    (
                        COALESCE(SUM(bt.distance_km),0) / NULLIF(b.mileage_kmpl, 0)
                    ) * COALESCE(fp.price_per_unit, 0),
                    2
                ) AS total_fuel_cost

            FROM bus_trip bt
            JOIN buses b ON b.id = bt.bus_id

            /* Latest fuel price applicable for that month */
            LEFT JOIN fuel_price fp
                ON fp.org_id = b.org_id
            AND fp.fuel_type = b.fuel_type
            AND fp.effective_from <= %s

            WHERE
                bt.trip_date BETWEEN %s AND %s
                AND b.org_id = %s
                AND bt.status = 'COMPLETED'

            GROUP BY
                b.id, b.bus_number, b.fuel_type, b.mileage_kmpl, fp.price_per_unit

            ORDER BY total_fuel_cost DESC
        """, (
            end_date,          # price effective till month end
            start_date,
            end_date,
            session["org_id"]
        ))

        reports = cursor.fetchall()

    finally:
        cursor.close()
        db.close()

    return render_template(
        "org/monthly_fuel_report.html",
        reports=reports,
        month=month,
        year=year
    )


@org_bp.route("/reports/fuel-monthly/pdf")
@login_required
def monthly_fuel_report_pdf():

    month = request.args.get("month")
    year = request.args.get("year")

    today = date.today()
    month = int(month) if month else today.month
    year = int(year) if year else today.year

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    db, cursor = get_cursor()
    cursor.execute("""
        SELECT
            b.bus_number,
            b.fuel_type,

            COUNT(bt.id) AS total_trips,
            COALESCE(SUM(bt.distance_km),0) AS total_distance_km,

            ROUND(
                COALESCE(SUM(bt.distance_km),0) / NULLIF(b.mileage_kmpl, 0),
                2
            ) AS total_fuel_used,

            ROUND(
                (
                    COALESCE(SUM(bt.distance_km),0) / NULLIF(b.mileage_kmpl, 0)
                ) * COALESCE(fp.price_per_unit, 0),
                2
            ) AS total_fuel_cost

        FROM bus_trip bt
        JOIN buses b ON b.id = bt.bus_id

        LEFT JOIN fuel_price fp
            ON fp.org_id = b.org_id
           AND fp.fuel_type = b.fuel_type
           AND fp.effective_from <= %s

        WHERE
            bt.trip_date BETWEEN %s AND %s
            AND b.org_id = %s
            AND bt.status = 'COMPLETED'

        GROUP BY
            b.id, b.bus_number, b.fuel_type, b.mileage_kmpl, fp.price_per_unit

        ORDER BY total_fuel_cost DESC
    """, (
        end_date,
        start_date,
        end_date,
        session["org_id"]
    ))

    rows = cursor.fetchall()
    cursor.close()
    db.close()

    # ================= PDF =================
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(
        f"<b>Monthly Fuel Cost Report</b><br/>{calendar.month_name[month]} {year}",
        styles["Title"]
    )
    elements.append(title)

    data = [
        ["Bus", "Fuel", "KM", "Fuel Used (L)", "Fuel Cost (₹)", "Trips"]
    ]

    for r in rows:
        data.append([
            r["bus_number"],
            r["fuel_type"],
            f"{r['total_distance_km']:.2f}",
            f"{r['total_fuel_used']:.2f}",
            f"₹ {r['total_fuel_cost']:.2f}",
            r["total_trips"]
        ])

    table = Table(data, colWidths=[90, 70, 70, 90, 100, 50])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,0), 10),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return Response(
        buffer,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            f"attachment;filename=Monthly_Fuel_Report_{month}_{year}.pdf"
        }
    )
