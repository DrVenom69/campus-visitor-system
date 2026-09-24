"""Admin: create host / security / admin accounts and switch accounts on or off."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.constants import CREATABLE_ROLES
from app.models import User
from app.utils import EMAIL_PATTERN, roles_required, staff_required

bp = Blueprint("users", __name__, url_prefix="/users")
admin_only = roles_required("admin")

MIN_PASSWORD_LENGTH = 8


def _profile_form():
    return {
        "name": request.form.get("name", current_user.name).strip(),
        "email": request.form.get("email", current_user.email).strip().lower(),
    }


@bp.route("/")
@admin_only
def index():
    users = User.query.order_by(User.role, User.name).all()
    return render_template("users/list.html", users=users)


@bp.route("/profile", methods=["GET", "POST"])
@staff_required
def profile():
    form = _profile_form()
    errors = {}

    if request.method == "POST":
        if not form["name"] or len(form["name"]) > 120:
            errors["name"] = "Enter a name (up to 120 characters)."
        if not EMAIL_PATTERN.match(form["email"]) or len(form["email"]) > 120:
            errors["email"] = "Enter a valid email address."
        else:
            existing = User.query.filter(User.email == form["email"], User.id != current_user.id).first()
            if existing:
                errors["email"] = "An account with this email already exists."

        if not errors:
            current_user.name = form["name"]
            current_user.email = form["email"]
            db.session.commit()
            flash("Your profile has been updated.", "success")
            return redirect(url_for("users.profile"))

    return render_template("users/profile.html", form=form, errors=errors, password_errors={}), (400 if errors else 200)


@bp.route("/profile/password", methods=["POST"])
@staff_required
def change_password():
    password_errors = {}
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.check_password(current_password):
        password_errors["current_password"] = "Your current password is incorrect."
    if len(new_password) < MIN_PASSWORD_LENGTH:
        password_errors["new_password"] = f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if new_password != confirm_password:
        password_errors["confirm_password"] = "Passwords do not match."

    if password_errors:
        return render_template(
            "users/profile.html",
            form={"name": current_user.name, "email": current_user.email},
            errors={},
            password_errors=password_errors,
        ), 400

    current_user.set_password(new_password)
    db.session.commit()
    flash("Your password has been changed.", "success")
    return redirect(url_for("users.profile"))


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
