from flask import render_template, request, redirect, session
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
import math


# =========================
# HELPER FUNCTION
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # KM
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# =========================
# ONE-TIME RECALC (OPTIONAL)
# =========================
def recalc_all_routes_distance():
    db, cursor = get_cursor()
    try:
        cursor.execute("SELECT DISTINCT route_id FROM route_stop")
        routes = cursor.fetchall()

        for r in routes:
            route_id = r["route_id"]

            cursor.execute("""
                SELECT latitude, longitude
                FROM route_stop
                WHERE route_id = %s
                ORDER BY stop_order
            """, (route_id,))
            stops = cursor.fetchall()

            total_km = 0
            for i in range(len(stops) - 1):
                total_km += haversine(
                    stops[i]["latitude"],
                    stops[i]["longitude"],
                    stops[i + 1]["latitude"],
                    stops[i + 1]["longitude"]
                )

            round_trip_km = total_km * 2

            cursor.execute("""
                UPDATE routes
                SET total_km = %s,
                    round_trip_km = %s
                WHERE id = %s
            """, (
                round(total_km, 2),
                round(round_trip_km, 2),
                route_id
            ))

        db.commit()
    finally:
        cursor.close()
        db.close()


# =========================
# VIEW + ADD ROUTE STOPS
# =========================
@org_bp.route("/routes/<int:route_id>/stops", methods=["GET", "POST"])
@login_required
def manage_route_stops(route_id):

    db, cursor = get_cursor()

    try:
        # =========================
        # ADD STOP
        # =========================
        if request.method == "POST":
            cursor.execute("""
                INSERT INTO route_stop
                (org_id, route_id, stop_name, latitude, longitude, stop_order)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                session["org_id"],
                route_id,
                request.form["stop_name"],
                float(request.form["latitude"]),
                float(request.form["longitude"]),
                request.form["stop_order"]
            ))
            db.commit()

            # 🔹 RECALCULATE DISTANCE
            cursor.execute("""
                SELECT latitude, longitude
                FROM route_stop
                WHERE route_id = %s
                ORDER BY stop_order
            """, (route_id,))
            stops = cursor.fetchall()

            total_km = 0
            for i in range(len(stops) - 1):
                total_km += haversine(
                    stops[i]["latitude"],
                    stops[i]["longitude"],
                    stops[i + 1]["latitude"],
                    stops[i + 1]["longitude"]
                )

            round_trip_km = total_km * 2

            cursor.execute("""
                UPDATE routes
                SET total_km = %s,
                    round_trip_km = %s
                WHERE id = %s AND org_id = %s
            """, (
                round(total_km, 2),
                round(round_trip_km, 2),
                route_id,
                session["org_id"]
            ))
            db.commit()

            return redirect(f"/org/routes/{route_id}/stops")

        # =========================
        # ROUTE INFO
        # =========================
        cursor.execute("""
            SELECT route_name, start_point, end_point
            FROM routes
            WHERE id = %s AND org_id = %s
        """, (route_id, session["org_id"]))
        route = cursor.fetchone()

        # =========================
        # ROUTE STOPS LIST
        # =========================
        cursor.execute("""
            SELECT id, stop_order, stop_name, latitude, longitude
            FROM route_stop
            WHERE route_id = %s
            ORDER BY stop_order
        """, (route_id,))
        stops = cursor.fetchall()

        return render_template(
            "org/org_route_stop_manage.html",
            route=route,
            route_id=route_id,
            stops=stops
        )

    finally:
        cursor.close()
        db.close()


# =========================
# DELETE ROUTE STOP
# =========================
@org_bp.route("/routes/stops/<int:id>/delete", methods=["POST"])
@login_required
def delete_route_stop_only(id):

    db, cursor = get_cursor()

    try:
        cursor.execute(
            "SELECT route_id FROM route_stop WHERE id = %s",
            (id,)
        )
        row = cursor.fetchone()
        route_id = row["route_id"] if row else None

        cursor.execute(
            "DELETE FROM route_stop WHERE id = %s",
            (id,)
        )
        db.commit()

        if route_id:
            cursor.execute("""
                SELECT latitude, longitude
                FROM route_stop
                WHERE route_id = %s
                ORDER BY stop_order
            """, (route_id,))
            stops = cursor.fetchall()

            total_km = 0
            for i in range(len(stops) - 1):
                total_km += haversine(
                    stops[i]["latitude"],
                    stops[i]["longitude"],
                    stops[i + 1]["latitude"],
                    stops[i + 1]["longitude"]
                )

            round_trip_km = total_km * 2

            cursor.execute("""
                UPDATE routes
                SET total_km = %s,
                    round_trip_km = %s
                WHERE id = %s AND org_id = %s
            """, (
                round(total_km, 2),
                round(round_trip_km, 2),
                route_id,
                session["org_id"]
            ))
            db.commit()

        return redirect(request.referrer)

    finally:
        cursor.close()
        db.close()
