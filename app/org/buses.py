from flask import flash, render_template, request, redirect, session
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp


# =========================
# BUS MANAGEMENT
# =========================
@org_bp.route("/buses")
@login_required
def org_buses():
    db, cursor = get_cursor()
    try:
        cursor.execute("""
            SELECT 
                b.id,
                b.bus_code,
                b.bus_number,
                b.bus_model,
                b.capacity,
                b.fuel_type,
                b.mileage_kmpl,
                b.status,

                fp.price_per_unit AS fuel_price
            FROM buses b
            LEFT JOIN fuel_price fp
                ON fp.org_id = b.org_id
                AND fp.fuel_type = b.fuel_type
                AND fp.effective_from = (
                    SELECT MAX(effective_from)
                    FROM fuel_price
                    WHERE org_id = b.org_id
                    AND fuel_type = b.fuel_type
                )
            WHERE b.org_id = %s
        """, (session["org_id"],))

        buses = cursor.fetchall()
        return render_template(
            "org/org_bus_manage.html",
            buses=buses
        )
    finally:
        cursor.close()
        db.close()


# =========================
# ADD BUS
# =========================
@org_bp.route("/buses/add", methods=["GET", "POST"])
@login_required
def add_bus():
    if request.method == "POST":
        db, cursor = get_cursor()
        try:
            cursor.execute("""
                INSERT INTO buses (
                    org_id,
                    bus_code,
                    bus_number,
                    bus_model,
                    capacity,
                    fuel_type,
                    mileage_kmpl,
                    status
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session["org_id"],
                request.form.get("bus_code"),
                request.form["bus_number"],
                request.form["bus_model"],
                request.form["capacity"],
                request.form["fuel_type"],
                request.form["mileage_kmpl"],
                request.form["status"]
            ))
            db.commit()
            return redirect("/org/buses")
        finally:
            cursor.close()
            db.close()

    return render_template("org/add_bus.html")


# =========================
# TOGGLE BUS STATUS (3-STATE)
# =========================
@org_bp.route("/buses/<int:id>/toggle")
@login_required
def toggle_bus(id):
    db, cursor = get_cursor()
    try:
        cursor.execute("""
            UPDATE buses
            SET status = CASE
                WHEN status = 'ACTIVE' THEN 'INACTIVE'
                WHEN status = 'INACTIVE' THEN 'MAINTENANCE'
                WHEN status = 'MAINTENANCE' THEN 'ACTIVE'
                ELSE 'ACTIVE'
            END
            WHERE id = %s
              AND org_id = %s
        """, (id, session["org_id"]))

        db.commit()
        return redirect("/org/buses")
    finally:
        cursor.close()
        db.close()


# =========================
# DELETE BUS
# =========================
@org_bp.route("/buses/<int:id>/delete")
@login_required
def delete_bus(id):
    db, cursor = get_cursor()
    try:
        cursor.execute("""
            DELETE FROM buses
            WHERE id = %s
              AND org_id = %s
        """, (id, session["org_id"]))

        db.commit()
        return redirect("/org/buses")
    finally:
        cursor.close()
        db.close()

@org_bp.route("/fuel-price", methods=["GET","POST"])
@login_required
def fuel_price_manage():
    db, cursor = get_cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO fuel_price (
                org_id, fuel_type, price_per_unit, effective_from
            )
            VALUES (%s,%s,%s,%s)
        """, (
            session["org_id"],
            request.form["fuel_type"],
            request.form["price_per_unit"],
            request.form["effective_from"]
        ))
        db.commit()

    cursor.execute("""
        SELECT fuel_type, price_per_unit, effective_from
        FROM fuel_price
        WHERE org_id=%s
        ORDER BY effective_from DESC
    """, (session["org_id"],))

    prices = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("org/fuel_price.html", prices=prices)


# ================================
# SAVE FUEL PRICE (ORG ADMIN)
# ================================
@org_bp.route("/fuel-price/save", methods=["POST"])
@login_required
def save_fuel_price():

    org_id = session["org_id"]
    fuel_type = request.form.get("fuel_type")
    price_per_unit = request.form.get("price_per_unit")
    effective_from = request.form.get("effective_from")

    if not fuel_type or not price_per_unit or not effective_from:
        flash("All fuel price fields are required", "danger")
        return redirect("/org/buses")

    db, cursor = get_cursor()
    try:
        cursor.execute("""
            INSERT INTO fuel_price (
                org_id,
                fuel_type,
                price_per_unit,
                effective_from
            )
            VALUES (%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                price_per_unit = VALUES(price_per_unit)
        """, (
            org_id,
            fuel_type,
            price_per_unit,
            effective_from
        ))

        db.commit()
        flash(f"{fuel_type} price saved successfully", "success")

    finally:
        cursor.close()
        db.close()

    return redirect("/org/buses")


# =========================
# EDIT BUS
# =========================
@org_bp.route("/buses/<int:id>/edit", methods=["GET","POST"])
@login_required
def edit_bus(id):
    db, cursor = get_cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE buses
            SET bus_code=%s,
                bus_number=%s,
                bus_model=%s,
                capacity=%s,
                fuel_type=%s,
                mileage_kmpl=%s,
                status=%s
            WHERE id=%s AND org_id=%s
        """, (
            request.form["bus_code"],
            request.form["bus_number"],
            request.form["bus_model"],
            request.form["capacity"],
            request.form["fuel_type"],
            request.form["mileage_kmpl"],
            request.form["status"],
            id,
            session["org_id"]
        ))
        db.commit()
        return redirect("/org/buses")

    cursor.execute("""
        SELECT *
        FROM buses
        WHERE id=%s AND org_id=%s
    """, (id, session["org_id"]))
    bus = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template("org/edit_bus.html", bus=bus)
