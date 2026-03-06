from flask import jsonify, render_template, session
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp


# =========================================================
# API: LIVE BUS STATUS (ORG DASHBOARD TABLE)
# =========================================================
@org_bp.route("/api/live-bus-status")
@login_required
def live_bus_status():
    org_id = session.get("org_id")

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT DISTINCT
            b.id AS bus_id,
            b.bus_number,
            u.name AS driver_name,
            lu.latitude,
            lu.longitude,
            lu.event_time AS last_updated,
            UPPER(
                CASE
                    WHEN lu.event_time IS NULL THEN 'OFFLINE'
                    WHEN TIMESTAMPDIFF(SECOND, lu.event_time, NOW()) <= 30
                        THEN 'RUNNING'
                    WHEN TIMESTAMPDIFF(SECOND, lu.event_time, NOW()) <= 180
                        THEN 'IDLE'
                    ELSE 'OFFLINE'
                END
            ) AS live_status
        FROM buses b
        INNER JOIN driver_assignment da
            ON da.bus_id = b.id
            AND da.status = 'ASSIGNED'
            AND da.assignment_date = CURDATE()
        LEFT JOIN users u
            ON u.id = da.driver_id
        LEFT JOIN location_update lu
            ON lu.id = (
                SELECT id
                FROM location_update
                WHERE bus_id = b.id
                ORDER BY event_time DESC
                LIMIT 1
            )
        WHERE b.org_id = %s
        ORDER BY b.bus_number
    """, (org_id,))

    rows = cursor.fetchall()
    cursor.close()
    db.close()

    data = []
    for r in rows:
        data.append({
            "bus_id": r["bus_id"],
            "bus_number": r["bus_number"],
            "driver_name": r["driver_name"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "last_updated": (
                r["last_updated"].strftime("%Y-%m-%d %H:%M:%S")
                if r["last_updated"] else None
            ),
            "live_status": r["live_status"]
        })

    return jsonify(data)


# =========================================================
# API: SINGLE BUS LIVE LOCATION (USED BY MAP PAGE)
# =========================================================
@org_bp.route("/api/bus-location/<int:bus_id>")
@login_required
def bus_location(bus_id):
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT latitude, longitude, event_time
        FROM location_update
        WHERE bus_id = %s
        ORDER BY event_time DESC
        LIMIT 1
    """, (bus_id,))

    row = cursor.fetchone()
    cursor.close()
    db.close()

    if not row:
        return jsonify({})

    return jsonify({
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "event_time": row["event_time"].strftime("%Y-%m-%d %H:%M:%S")
    })


# =========================================================
# PAGE: FULL-SCREEN LIVE MAP FOR A SINGLE BUS
# =========================================================
@org_bp.route("/bus-live-map/<int:bus_id>")
@login_required
def bus_live_map(bus_id):
    return render_template(
        "org/org_live_map.html",
        bus_id=bus_id
    )


# =========================================================
# API: BUS ROUTE STOPS
# =========================================================
@org_bp.route("/api/bus-route/<int:bus_id>")
@login_required
def bus_route(bus_id):
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT rs.stop_name, rs.latitude, rs.longitude
        FROM route_stop rs
        INNER JOIN driver_assignment da ON da.route_id = rs.route_id
        WHERE da.bus_id = %s
          AND da.assignment_date = CURDATE()
        ORDER BY rs.stop_order
    """, (bus_id,))

    rows = cursor.fetchall()
    cursor.close()
    db.close()

    stops = []
    for r in rows:
        stops.append({
            "name": r["stop_name"],
            "latitude": r["latitude"],
            "longitude": r["longitude"]
        })

    return jsonify(stops)


# =========================================================
# PAGE: VIEW LOCATION FROM NOTIFICATION
# =========================================================
@org_bp.route("/view-location/<int:notification_id>")
@login_required
def view_notification_location(notification_id):

    db, cursor = get_cursor()
    cursor.execute("""
        SELECT latitude, longitude, accuracy, title, message, event_time
        FROM notifications
        WHERE id=%s AND org_id=%s
    """, (notification_id, session["org_id"]))

    row = cursor.fetchone()
    cursor.close()
    db.close()

    if not row or not row["latitude"] or not row["longitude"]:
        return "Location not available", 404

    return render_template(
        "org/notification_map.html",
        latitude=row["latitude"],
        longitude=row["longitude"],
        accuracy=row["accuracy"] or 0,
        title=row["title"],
        message=row["message"],
        event_time=row["event_time"]
    )
