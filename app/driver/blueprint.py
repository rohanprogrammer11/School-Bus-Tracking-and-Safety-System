from flask import Blueprint

# =========================
# DRIVER BLUEPRINT
# =========================
driver_bp = Blueprint("driver", __name__, url_prefix="/driver")

# =========================
# IMPORT ROUTES
# (IMPORTANT: These imports REGISTER routes)
# =========================
from app.driver import dashboard
from app.driver import notifications
