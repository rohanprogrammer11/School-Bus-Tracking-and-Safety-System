from email.message import EmailMessage
import secrets
import smtplib
from flask import render_template, request, redirect, flash, session, url_for
from werkzeug.security import generate_password_hash
from app.extensions import get_cursor, login_required
from app.org.blueprint import org_bp
import re


@org_bp.route("/dashboard")
@login_required
def dashboard():
    org_id = session.get("org_id")

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT org_name, udise_code
        FROM organization
        WHERE id = %s
    """, (org_id,))

    org = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template(
        "org/org_dashboard.html",
        org_name=org["org_name"] if org else "",
        udise_code=org["udise_code"] if org else ""
    )


@org_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":
        email = request.form.get("email")

        db, cursor = get_cursor()
        cursor.execute("SELECT id FROM organization WHERE email = %s", (email,))
        org = cursor.fetchone()

        if not org:
            flash("Email not registered.")
            cursor.close()
            db.close()
            return redirect(url_for("org.forgot_password"))

        token = secrets.token_urlsafe(32)

        session["reset_token"] = token
        session["reset_org_id"] = org["id"]

        reset_link = url_for("org.reset_password", token=token, _external=True)

        msg = EmailMessage()
        msg["Subject"] = "Password Reset Link"
        msg["From"] = "schoolbustracking000@gmail.com"
        msg["To"] = email
        msg.set_content(f"Click this link to reset password:\n{reset_link}")

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login("schoolbustracking000@gmail.com", "fohu hszp uqpq axng")
                server.send_message(msg)
        except Exception as e:
            print("Email error:", e)

        flash("Reset link sent to your email.")
        cursor.close()
        db.close()
        return redirect(url_for("org.forgot_password"))

    return render_template("forgot_password.html")

#---------------------------------
#
#------------------------------
@org_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    if "reset_org_id" not in session:
        flash("Session expired. Try again.", "error")
        return redirect(url_for("org.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        # Match check
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")

        # =========================
        # STRONG PASSWORD VALIDATION
        # =========================

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[A-Z]', new_password):
            flash("Password must contain at least one uppercase letter.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[a-z]', new_password):
            flash("Password must contain at least one lowercase letter.", "error")
            return render_template("reset_password.html")

        if not re.search(r'\d', new_password):
            flash("Password must contain at least one number.", "error")
            return render_template("reset_password.html")

        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', new_password):
            flash("Password must contain at least one special character.", "error")
            return render_template("reset_password.html")

        # =========================
        # UPDATE PASSWORD
        # =========================

        db, cursor = get_cursor()
        hashed_password = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password_hash = %s
            WHERE org_id = %s AND role = 'admin'
        """, (hashed_password, session["reset_org_id"]))

        db.commit()
        cursor.close()
        db.close()

        session.pop("reset_org_id", None)

        flash("Password reset successful. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")