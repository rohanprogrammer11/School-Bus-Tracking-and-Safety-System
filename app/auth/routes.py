from flask import Blueprint, flash, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import get_cursor
import re
import random
import time
import smtplib
from email.message import EmailMessage

auth_bp = Blueprint("auth", __name__)

#-------------------------
#
#-------------------------
def send_otp_email(to_email, otp):
    try:
        msg = EmailMessage()
        msg["Subject"] = "School Bus Safety - Email Verification OTP"
        msg["From"] = "schoolbustracking000@gmail.com"
        msg["To"] = to_email

        msg.set_content(f"""
Hello,

Your OTP for Organization Registration is:

{otp}

This OTP is valid for 5 minutes.

If you did not request this, please ignore this email.
""")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("schoolbustracking000@gmail.com", "fohu hszp uqpq axng")
            server.send_message(msg)

        print("✅ OTP Email Sent Successfully")

    except Exception as e:
        print("❌ Email Sending Failed:", e)
        raise


#------------------------------
#
#------------------------------
@auth_bp.route("/verify-org-otp", methods=["GET", "POST"])
def verify_org_otp():
    if request.method == "POST":
        entered_otp = request.form["otp"]

        # Check expiry (5 minutes)
        if time.time() - session.get("otp_time", 0) > 300:
            flash("OTP expired. Please register again.", "error")
            return redirect("/signup")


        if entered_otp != session.get("otp"):
            flash("Invalid OTP. Please try again.", "error")
            return redirect("/verify-org-otp")

        data = session.get("temp_org_data")
        if not data:
            return redirect("/signup")

        db, cursor = get_cursor()

        password_hash = generate_password_hash(data["password"])

        # Insert organization
        cursor.execute("""
            INSERT INTO organization
            (org_name, udise_code, address, email, phone, principal_name, password)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            data["org_name"],
            data["udise_code"],
            data["address"],
            data["email"],
            data["phone"],
            data["principal_name"],
            password_hash
        ))
        db.commit()
        org_id = cursor.lastrowid

        # Insert admin user
        cursor.execute("""
            INSERT INTO users
            (org_id, name, email, phone, role, password_hash)
            VALUES (%s,%s,%s,%s,'admin',%s)
        """, (
            org_id,
            data["org_name"],
            data["email"],
            data["phone"],
            password_hash
        ))
        db.commit()

        cursor.close()
        db.close()

        # Clear temporary session data
        session.pop("otp", None)
        session.pop("otp_time", None)
        session.pop("temp_org_data", None)

        return redirect("/login")

    return render_template(
        "verify_otp.html",
        user_type="Organization",
        resend_url="/resend-org-otp"
    )

#----------------------
#
#---------------------
@auth_bp.route("/resend-org-otp")
def resend_org_otp():

    data = session.get("temp_org_data")

    if not data:
        flash("Session expired. Please register again.", "error")
        return redirect("/signup")

    # Generate new OTP
    otp = str(random.randint(100000, 999999))

    session["otp"] = otp
    session["otp_time"] = time.time()

    # Send new OTP
    send_otp_email(data["email"], otp)

    flash("New OTP sent to your email.", "success")
    return redirect("/verify-org-otp")





# =========================
# LANDING PAGE
# =========================
@auth_bp.route("/", methods=["GET"])
def landing():
    return render_template("landing_page.html")

# =========================
# SIGNUP (ORG)
# =========================
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        org_name = request.form["org_name"]
        udise_code = request.form["udise_code"]
        address = request.form["address"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]
        principal_name = request.form.get("principal_name")

        password_hash = generate_password_hash(password)

        db, cursor = get_cursor()

        # Check email
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            cursor.close()
            db.close()
            return render_template(
                "org/org_register.html",
                form_data=request.form,
                errors={"email": "Email already registered."}
            )

        # Check UDISE
        cursor.execute("SELECT id FROM organization WHERE udise_code=%s", (udise_code,))
        if cursor.fetchone():
            cursor.close()
            db.close()
            return render_template(
                "org/org_register.html",
                form_data=request.form,
                errors={"udise_code": "UDISE Code already registered."}
            )

        # =========================
        # BASIC VALIDATION
        # =========================

        # Email format check
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            flash("Invalid email format (example: school@gmail.com)", "error")
            return render_template("org/org_register.html", form_data=request.form)

        # Phone number check (10 digits only)
        if not re.fullmatch(r'\d{6,11}', phone):
            return render_template(
                "org/org_register.html",
                form_data=request.form,
                errors={"phone": "Phone number must be between 6 and 11 digits."}
            )



        # =========================
        # STRONG PASSWORD VALIDATION
        # =========================

        if len(password) < 8:
            return "❌ Password must be at least 8 characters"

        if not re.search(r'[A-Z]', password):
            return "❌ Password must contain at least one uppercase letter"

        if not re.search(r'[a-z]', password):
            return "❌ Password must contain at least one lowercase letter"

        if not re.search(r'\d', password):
            return "❌ Password must contain at least one number"

        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
            return "❌ Password must contain at least one special character"

        # 🔐 Generate OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP and form data in session
        session["otp"] = otp
        session["otp_time"] = time.time()

        session["temp_org_data"] = {
            "org_name": org_name,
            "udise_code": udise_code,
            "address": address,
            "email": email,
            "phone": phone,
            "password": password,
            "principal_name": principal_name
        }

        # Send OTP
        send_otp_email(email, otp)

        return redirect("/verify-org-otp")

    return render_template("org/org_register.html")

# =========================
# ADMIN LOGIN
# =========================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form["identifier"]
        password = request.form["password"]

        db, cursor = get_cursor()

        cursor.execute("""
            SELECT u.id, u.org_id, u.name, u.role, u.password_hash, o.org_name
            FROM users u
            JOIN organization o ON o.id = u.org_id
            WHERE (u.email=%s OR u.phone=%s)
              AND u.role='admin'
        """, (identifier, identifier))

        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["org_id"] = user["org_id"]
            session["admin_name"] = user["name"]
            session["role"] = user["role"]
            session["org_name"] = user["org_name"]
            return redirect("/org/dashboard")

        flash("Login failed. Please check your email/phone and password.", "error")
        return render_template("org/org_login.html")




    return render_template("org/org_login.html")

# =========================
# DRIVER LOGIN
# =========================
@auth_bp.route("/driver/login", methods=["GET", "POST"])
def driver_login():
    if request.method == "POST":
        identifier = request.form["identifier"]
        password = request.form["password"]

        db, cursor = get_cursor()

        cursor.execute("""
            SELECT id, org_id, name, role, password_hash
            FROM users
            WHERE (email=%s OR phone=%s)
              AND role='driver'
        """, (identifier, identifier))

        driver = cursor.fetchone()
        cursor.close()
        db.close()

        if driver and check_password_hash(driver["password_hash"], password):
            session.clear()
            session["user_id"] = driver["id"]
            session["org_id"] = driver["org_id"]
            session["driver_name"] = driver["name"]
            session["role"] = driver["role"]
            return redirect("/driver/dashboard")

        return "❌ Invalid driver credentials"

    return render_template("driver/driver_login.html")

# =========================
# LOGOUT
# =========================
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =====================================
# PARENT REGISTER (OTP FLOW)
# =====================================
@auth_bp.route("/parent/register", methods=["GET", "POST"])
def parent_register():
    db, cursor = get_cursor()

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]
        org_id = int(request.form["org_id"])



        rfid = request.form.get("rfid_tag")
        qr = request.form.get("qr_code")

        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            cursor.close()
            db.close()
            return "Email already registered"

        # Validation
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            return "Invalid email"

        if not re.fullmatch(r'\d{10}', phone):
            return "Phone must be 10 digits"

        if len(password) < 8:
            return "Password must be 8 characters"

        # 🔐 Generate OTP
        otp = str(random.randint(100000, 999999))

        session["parent_otp"] = otp
        session["parent_otp_time"] = time.time()

        session["temp_parent_data"] = {
            "org_id": org_id,
            "name": name,
            "email": email,
            "phone": phone,
            "password": password,
            "rfid": rfid,
            "qr": qr
        }

        send_otp_email(email, otp)

        cursor.close()
        db.close()

        return redirect("/verify-parent-otp")

    cursor.execute("SELECT id, org_name FROM organization ORDER BY org_name")
    organizations = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("parent/parent_register.html", organizations=organizations)


# =====================================
# VERIFY PARENT OTP (AUTO LINK HERE)
# =====================================
@auth_bp.route("/verify-parent-otp", methods=["GET", "POST"])
def verify_parent_otp():
    if request.method == "POST":
        entered_otp = request.form["otp"]

        if time.time() - session.get("parent_otp_time", 0) > 300:
            flash("OTP expired.", "error")
            return redirect("/parent/register")

        if entered_otp != session.get("parent_otp"):
            flash("Invalid OTP.", "error")
            return redirect("/verify-parent-otp")

        data = session.get("temp_parent_data")
        if not data:
            return redirect("/parent/register")

        db, cursor = get_cursor()

        password_hash = generate_password_hash(data["password"])

        # Insert parent
        cursor.execute("""
            INSERT INTO users
            (org_id, name, email, phone, role, password_hash)
            VALUES (%s,%s,%s,%s,'parent',%s)
        """, (
            data["org_id"],
            data["name"],
            data["email"],
            data["phone"],
            password_hash
        ))

        parent_id = cursor.lastrowid

        # 🔥 FIND STUDENT
        student = None

        if data["rfid"]:
            cursor.execute("""
                SELECT id FROM student
                WHERE org_id=%s AND rfid_tag=%s
            """, (data["org_id"], data["rfid"]))
            student = cursor.fetchone()

        elif data["qr"]:
            cursor.execute("""
                SELECT id FROM student
                WHERE org_id=%s AND qr_code=%s
            """, (data["org_id"], data["qr"]))
            student = cursor.fetchone()

        print("Student Found:", student)

        # 🔥 LINK IF FOUND
        if student:
            student_id = student["id"]

            cursor.execute("""
                INSERT INTO parent_student (parent_id, student_id)
                VALUES (%s, %s)
            """, (parent_id, student_id))

            cursor.execute("""
                UPDATE student
                SET parent_id=%s
                WHERE id=%s
            """, (parent_id, student_id))

        db.commit()
        cursor.close()
        db.close()

        session.clear()
        return redirect("/parent/login")

    return render_template(
        "verify_otp.html",
        user_type="Parent",
        resend_url="/resend-parent-otp"
    )


# =====================================
# RESEND PARENT OTP
# =====================================
@auth_bp.route("/resend-parent-otp")
def resend_parent_otp():
    data = session.get("temp_parent_data")

    if not data:
        flash("Session expired.", "error")
        return redirect("/parent/register")

    otp = str(random.randint(100000, 999999))
    session["parent_otp"] = otp
    session["parent_otp_time"] = time.time()

    send_otp_email(data["email"], otp)
    flash("New OTP sent.", "success")

    return redirect("/verify-parent-otp")


# =========================
# PARENT LOGIN
# =========================
@auth_bp.route("/parent/login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        identifier = request.form["identifier"]
        password = request.form["password"]

        db, cursor = get_cursor()
        cursor.execute("""
            SELECT id, org_id, name, role, password_hash
            FROM users
            WHERE (email=%s OR phone=%s)
              AND role='parent'
        """, (identifier, identifier))

        parent = cursor.fetchone()
        cursor.close()
        db.close()

        if parent and check_password_hash(parent["password_hash"], password):
            session.clear()
            session.update({
                "user_id": parent["id"],
                "org_id": parent["org_id"],
                "parent_name": parent["name"],
                "role": parent["role"]
            })
            return redirect("/parent/dashboard")

        return "❌ Invalid parent credentials"

    return render_template("parent/parent_login.html")
