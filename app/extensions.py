import mysql.connector
from flask import session, redirect, request
from functools import wraps

# =========================
# DB FACTORY (SAFE)
# =========================
def get_cursor():
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="rohan050@",
        database="school_bus_safety",
        autocommit=False
    )
    
    cursor = db.cursor(dictionary=True, buffered=True)
    return db, cursor


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):

            # ✅ FIX: If request comes from fetch / AJAX, return JSON
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"status": "Unauthorized"}, 401

            # Normal browser navigation
            if request.path.startswith("/driver"):
                return redirect("/driver/login")
            if request.path.startswith("/parent"):
                return redirect("/parent/login")
            return redirect("/login")

        return f(*args, **kwargs)
    return wrapper
