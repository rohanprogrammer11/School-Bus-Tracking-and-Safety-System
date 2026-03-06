from flask import Flask
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "app", "templates"),
    static_folder=os.path.join(BASE_DIR, "app", "static")
)

app.secret_key = "your-secret-key"

from app.auth.routes import auth_bp
from app.parent.blueprint import parent_bp
from app.driver.blueprint import driver_bp
from app.org.blueprint import org_bp

app.register_blueprint(auth_bp)
app.register_blueprint(parent_bp, url_prefix="/parent")
app.register_blueprint(driver_bp, url_prefix="/driver")
app.register_blueprint(org_bp, url_prefix="/org")
if __name__ == "__main__":
    app.run(debug=True)
