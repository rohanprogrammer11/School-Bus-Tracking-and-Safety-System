from flask import render_template, request, session, redirect, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import login_required, get_cursor
from app.org.blueprint import org_bp
import uuid
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage


# =========================
# ORGANIZATION PROFILE
# =========================
@org_bp.route("/profile", methods=["GET", "POST"])
@login_required
def org_profile():
    org_id = session["org_id"]
    db, cursor = get_cursor()

    # -------------------------
    # UPDATE PROFILE
    # -------------------------
    if request.method == "POST":
        email = request.form.get("email")
        phone = request.form.get("phone")
        principal_name = request.form.get("principal_name")

        cursor.execute("""
            UPDATE organization
            SET email=%s,
                phone=%s,
                principal_name=%s
            WHERE id=%s
        """, (email, phone, principal_name, org_id))

        db.commit()
        cursor.close()
        db.close()

        flash("Profile updated successfully", "success")
        return redirect("/org/profile")

    # -------------------------
    # FETCH PROFILE
    # -------------------------
    cursor.execute("""
        SELECT org_name, udise_code, email, phone, principal_name
        FROM organization
        WHERE id=%s
    """, (org_id,))
    org = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template("org/org_profile.html", org=org)


# =========================
# SEND RESET EMAIL
# =========================
def send_reset_email(to_email, reset_link):
    msg = EmailMessage()
    msg["Subject"] = "Reset Your Password"
    msg["Bcc"] = "schoolbustracking000@gmail.com"
    msg["To"] = to_email

    msg.set_content(f"""
Hello,

You requested to reset your password.

Click the link below to reset it:
{reset_link}

This link is valid for 15 minutes.

If you did not request this, please ignore this email.
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("schoolbustracking000@gmail.com", "fohu hszp uqpq axng")
        server.send_message(msg)


# =========================
# DELETE ORGANIZATION
# =========================
@org_bp.route("/delete", methods=["POST"])
@login_required
def delete_organization():
    if session.get("role") != "admin":
        flash("Unauthorized action", "error")
        return redirect("/org/profile")

    org_id = session.get("org_id")
    password = request.form.get("password")

    db, cursor = get_cursor()

    cursor.execute("""
        SELECT password_hash
        FROM users
        WHERE org_id=%s AND role='admin'
    """, (org_id,))
    admin = cursor.fetchone()

    if not admin or not check_password_hash(admin["password_hash"], password):
        cursor.close()
        db.close()
        flash("Incorrect password. Organization not deleted.", "error")
        return redirect("/org/profile")

    cursor.execute("""
        DELETE FROM organization
        WHERE id=%s
    """, (org_id,))

    db.commit()
    cursor.close()
    db.close()

    session.clear()
    return redirect("/")
