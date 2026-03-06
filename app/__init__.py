from flask import Flask
from datetime import timedelta
from flask_mail import Mail

mail = Mail()


def create_app():
    app = Flask(__name__)

    # 🔐 FIXED SECRET KEY (GOOD)
    app.secret_key = "school_bus_safety"
    
     # 🔐 SESSION STABILITY FIX
    app.config.update(
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",   # 🔥 REQUIRED
    )

    # =========================
    # REGISTER AUTH BLUEPRINT
    # =========================
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)

    # =========================
    # REGISTER ORG BLUEPRINT
    # =========================
    from app.org.blueprint import org_bp
    app.register_blueprint(org_bp)

    # =========================
    # REGISTER DRIVER BLUEPRINT
    # =========================
    from app.driver.blueprint import driver_bp
    app.register_blueprint(driver_bp)

    # =========================
    # PARENT DASHBOARD BLUEPRINT
    # =========================
    from app.parent.blueprint import parent_bp
    app.register_blueprint(parent_bp)

    return app