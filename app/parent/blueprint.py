from flask import Blueprint

parent_bp = Blueprint(
    "parent",
    __name__,
    url_prefix="/parent"
)

# ================================
# IMPORT ROUTES (VERY IMPORTANT)
# ================================
from . import dashboard
from . import notifications
from . import parent_profile
