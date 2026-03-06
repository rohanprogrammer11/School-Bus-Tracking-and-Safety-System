from flask import render_template, request, redirect, session
from datetime import datetime, timedelta
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask import Response
import io
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle



# =========================
# ROUTES MANAGEMENT
# =========================
@org_bp.route("/routes")
@login_required
def org_routes():
    db, cursor = get_cursor()

    try:
        cursor.execute("""
            SELECT
                id,
                route_code,
                route_name,
                start_point,
                end_point,
                start_time,
                drop_time,
                total_km,
                round_trip_km
            FROM routes
            WHERE org_id = %s
        """, (session["org_id"],))

        rows = cursor.fetchall()
        routes = []

        def fmt(t):
            if isinstance(t, timedelta):
                seconds = int(t.total_seconds())
                return datetime.strptime(
                    f"{seconds//3600}:{(seconds % 3600)//60}",
                    "%H:%M"
                ).strftime("%I:%M %p")
            return t

        for r in rows:
            cursor.execute("""
                SELECT id, stop_name, latitude, longitude, stop_order
                FROM route_stop
                WHERE route_id = %s
                ORDER BY stop_order
            """, (r["id"],))

            routes.append({
                "id": r["id"],
                "route_code": r["route_code"],
                "route_name": r["route_name"],
                "start_point": r["start_point"],
                "end_point": r["end_point"],
                "start_time": fmt(r["start_time"]),
                "drop_time": fmt(r["drop_time"]),
                "total_km": r["total_km"],
                "round_trip_km": r["round_trip_km"],
                "stops": cursor.fetchall()
            })

        return render_template(
            "org/org_route_manage.html",
            routes=routes
        )

    finally:
        cursor.close()
        db.close()


# =========================
# ADD ROUTE
# =========================
@org_bp.route("/routes/add", methods=["GET", "POST"])
@login_required
def add_route():
    if request.method == "POST":
        db, cursor = get_cursor()
        try:
            cursor.execute("""
                INSERT INTO routes
                (org_id, route_code, route_name, start_point, end_point, start_time, drop_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                session["org_id"],
                request.form["route_code"],
                request.form["route_name"],
                request.form["start_point"],
                request.form["end_point"],
                request.form["start_time"],
                request.form["drop_time"]
            ))
            db.commit()
            return redirect("/org/routes")
        finally:
            cursor.close()
            db.close()

    return render_template("org/add_route.html")


# =========================
# DELETE ROUTE
# =========================
@org_bp.route("/routes/<int:id>/delete")
@login_required
def delete_route(id):
    db, cursor = get_cursor()
    try:
        cursor.execute(
            "DELETE FROM routes WHERE id=%s AND org_id=%s",
            (id, session["org_id"])
        )
        db.commit()
        return redirect("/org/routes")
    finally:
        cursor.close()
        db.close()

#--------------
# Pdf report genrater
#-------------
@org_bp.route("/routes/report/pdf")
@login_required
def download_routes_pdf():
    
    def fmt_time(t):
        if isinstance(t, timedelta):
            seconds = int(t.total_seconds())
            return datetime.strptime(
                f"{seconds//3600}:{(seconds % 3600)//60}",
                "%H:%M"
            ).strftime("%I:%M %p")
        return t.strftime("%I:%M %p") if t else "-"

    db, cursor = get_cursor()

    try:
        cursor.execute(
            "SELECT org_name FROM organization WHERE id = %s",
            (session["org_id"],)
        )
        org_result = cursor.fetchone()
        org_name = org_result["org_name"] if org_result else "Organization"

        cursor.execute("""
            SELECT
                route_code,
                route_name,
                start_point,
                end_point,
                start_time,
                drop_time,
                total_km,
                round_trip_km
            FROM routes
            WHERE org_id = %s
        """, (session["org_id"],))

        rows = cursor.fetchall()

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()
        elements = []

        # Title
        header_style = ParagraphStyle(
            name="HeaderStyle",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
            spaceBefore=10
        )

        sub_header_style = ParagraphStyle(
            name="SubHeaderStyle",
            fontSize=11,
            alignment=TA_CENTER,
            textColor=colors.grey,
            spaceAfter=20
        )

        # 🔹 MAIN TITLE
        elements.append(Paragraph(
            "School Bus Route Distance Report",
            header_style
        ))

        # 🔹 ORGANIZATION NAME
        elements.append(Paragraph(
            f"<b>{org_name}</b>",
            sub_header_style
        ))

        elements.append(Paragraph("<br/>", styles["Normal"]))

        # Table header
        data = [[
            "Route Code",
            "Route Name",
            "Start",
            "End",
            "Pickup",
            "Drop",
            "One Way KM",
            "Round Trip KM"
        ]]

        for r in rows:
            data.append([
                r["route_code"],
                r["route_name"],
                r["start_point"],
                r["end_point"],
                str(r["start_time"]),
                str(r["drop_time"]),
                f"{r['total_km']} km",
                f"{r['round_trip_km']} km"
            ])

        table = Table(data, repeatRows=1)

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),

            ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ]))

        elements.append(table)
        pdf.build(elements)

        buffer.seek(0)

        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": "attachment;filename=route_distance_report.pdf"
            }
        )

    finally:
        cursor.close()
        db.close()
