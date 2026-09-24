"""Staff login and logout."""
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.models import User

bp = Blueprint("auth", __name__)


def _is_safe_next(target):
    """Only allow redirects to a path on this site (blocks open redirects)."""
    if not target or "\\" in target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.is_active and user.check_password(password):
            login_user(user)
            target = request.args.get("next") or request.form.get("next")
            return redirect(target if _is_safe_next(target) else url_for("dashboard.index"))

        flash("Email or password is incorrect.", "danger")
        return render_template("login.html", email=email), 401

    return render_template("login.html", email="")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("public.index"))
