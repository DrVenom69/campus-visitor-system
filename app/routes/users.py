"""Admin: create host / security / admin accounts and switch accounts on or off."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.constants import CREATABLE_ROLES
from app.models import User
from app.utils import EMAIL_PATTERN, roles_required

bp = Blueprint("users", __name__, url_prefix="/users")
admin_only = roles_required("admin")

MIN_PASSWORD_LENGTH = 8


@bp.route("/")
@admin_only
def index():
    users = User.query.order_by(User.role, User.name).all()
    return render_template("users/list.html", users=users)


@bp.route("/new", methods=["GET", "POST"])
@admin_only
def new():
    form = {key: request.form.get(key, "").strip() for key in ("name", "email", "role")}
    form["email"] = form["email"].lower()
    errors = {}

    if request.method == "POST":
        password = request.form.get("password", "")

        if not form["name"] or len(form["name"]) > 120:
            errors["name"] = "Enter a name (up to 120 characters)."
        if not EMAIL_PATTERN.match(form["email"]) or len(form["email"]) > 120:
            errors["email"] = "Enter a valid email address."
        elif User.query.filter_by(email=form["email"]).first():
            errors["email"] = "An account with this email already exists."
        if form["role"] not in CREATABLE_ROLES:
            errors["role"] = "Choose a role."
        if len(password) < MIN_PASSWORD_LENGTH:
            errors["password"] = f"Use at least {MIN_PASSWORD_LENGTH} characters."

        if not errors:
            user = User(name=form["name"], email=form["email"], role=form["role"])
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Account created for {user.name}.", "success")
            return redirect(url_for("users.index"))

    return render_template("users/form.html", form=form, errors=errors, roles=CREATABLE_ROLES), (400 if errors else 200)


@bp.route("/<int:user_id>/toggle", methods=["POST"])
@admin_only
def toggle(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f"{user.name} is now {'active' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("users.index"))
