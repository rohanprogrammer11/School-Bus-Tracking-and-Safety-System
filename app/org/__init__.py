from flask import Flask
# app/org/__init__.py
from . import profile

def create_app():
    app = Flask(__name__)
    app.secret_key = "school_bus_safety"


    # =========================
    # REGISTER AUTH BLUEPRINT
    # =========================
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)   # / , /login , /signup

    # =========================
    # REGISTER ORG BLUEPRINT
    # =========================
    from app.org.blueprint import org_bp
    app.register_blueprint(org_bp)    # /org/... (already defined)

    return app
