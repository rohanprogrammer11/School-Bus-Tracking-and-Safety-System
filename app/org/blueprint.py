from flask import Blueprint

# =========================
# ORG BLUEPRINT
# =========================
org_bp = Blueprint(
    "org",
    __name__,
    url_prefix="/org"
)

# =========================
# IMPORT ROUTES
# (IMPORTANT: These imports REGISTER routes)
# =========================
from app.org import (
    dashboard,
    profile,
    drivers,
    buses,
    routes,
    assignments,
    routes_stop,
    classes,
    students,
    notifications,
    live_location,
    driver_attendance,
    student_history,
    daily_report,
    stop_fee,
    fuel_reports
)
