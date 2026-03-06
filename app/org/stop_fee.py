from flask import render_template, session
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
from flask import request, redirect, flash


# =========================
# BUS STOP FEE LIST
# =========================
@org_bp.route("/stop-fees", methods=["GET"])
@login_required
def stop_fee_list():
    org_id = session.get("org_id")
    db, cursor = get_cursor()

    cursor.execute("""
        SELECT
            MIN(rs.id) AS id,
            rs.stop_name,
            MAX(rs.monthly_fee) AS monthly_fee
        FROM route_stop rs
        WHERE rs.org_id = %s
        GROUP BY rs.stop_name
        ORDER BY rs.stop_name
    """, (org_id,))

    stops = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "org/org_route_stop_fee.html",
        stops=stops
    )

# =========================
# UPDATE STOP FEE
# =========================
@org_bp.route("/stop-fees/update", methods=["POST"])
@login_required
def update_stop_fee():
    org_id = session.get("org_id")
    stop_id = request.form.get("stop_id")
    monthly_fee = request.form.get("monthly_fee")

    # Validation
    if not stop_id:
        flash("Invalid stop selected", "danger")
        return redirect("/org/stop-fees")

    try:
        monthly_fee = float(monthly_fee)
        if monthly_fee <= 0:
            raise ValueError
    except:
        flash("Enter a valid fee greater than 0", "danger")
        return redirect("/org/stop-fees")

    db, cursor = get_cursor()

    # 🔹 STEP 1: Fetch stop_name safely
    cursor.execute("""
        SELECT stop_name
        FROM route_stop
        WHERE id = %s AND org_id = %s
    """, (stop_id, org_id))

    row = cursor.fetchone()

    if not row:
        cursor.close()
        db.close()
        flash("Stop not found", "danger")
        return redirect("/org/stop-fees")

    stop_name = row["stop_name"]

    # 🔹 STEP 2: Update ALL same stop names
    cursor.execute("""
        UPDATE route_stop
        SET monthly_fee = %s
        WHERE stop_name = %s AND org_id = %s
    """, (monthly_fee, stop_name, org_id))

    db.commit()
    cursor.close()
    db.close()

    flash("Stop fee updated successfully", "success")
    return redirect("/org/stop-fees")
