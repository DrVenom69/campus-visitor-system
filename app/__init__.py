from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Bootstrap colour used for each status on the public pages.
_BOOTSTRAP_STATUS_COLORS = {
    "Pending": "warning",
    "Approved": "primary",
    "Rejected": "danger",
    "Cancelled": "secondary",
    "Checked In": "success",
    "Checked Out": "secondary",
    "Completed": "success",
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    from app import models  # noqa: F401  (registers the models and the user loader)
    from app.cli import register_cli
    from app.routes import register_blueprints
    from app.utils import to_local

    register_blueprints(app)
    register_cli(app)

    # ---- template helpers
    @app.template_filter("local_dt")
    def local_dt(value):
        """Stored UTC datetime -> '24 Sep 2026, 03:15 PM' in the campus timezone."""
        local = to_local(value)
        return local.strftime("%d %b %Y, %I:%M %p") if local else ""

    @app.template_filter("local_time")
    def local_time(value):
        local = to_local(value)
        return local.strftime("%I:%M %p") if local else ""

    @app.template_filter("bs_status")
    def bs_status(status):
        return _BOOTSTRAP_STATUS_COLORS.get(status, "secondary")

    @app.context_processor
    def inject_pending_count():
        """Number shown next to 'Requests' in the admin sidebar."""
        if current_user.is_authenticated and current_user.role == "admin":
            return {"pending_count": models.VisitRequest.query.filter_by(status="Pending").count()}
        return {}

    # ---- error pages
    @app.errorhandler(403)
    @app.errorhandler(404)
    def http_error(error):
        messages = {
            403: "You do not have permission to open this page.",
            404: "We could not find that page.",
        }
        return (
            render_template("error.html", code=error.code, message=messages[error.code]),
            error.code,
        )

    return app
