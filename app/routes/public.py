"""Pages anyone can open: home, visit request form, status lookup, digital gate pass."""
from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app import db
from app.constants import PURPOSES
from app.models import GatePass, Visitor, VisitRequest
from app.qr import qr_png
from app.utils import EMAIL_PATTERN, generate_request_id, today_local

bp = Blueprint("public", __name__)

PHONE_PATTERN_CHARS = set("0123456789+-() ")
MAX_DAYS_AHEAD = 90
FORM_FIELDS = (
    "full_name", "email", "phone", "organization",
    "purpose", "host_requested", "visit_date", "notes",
)


def _valid_phone(value):
    return 6 <= len(value) <= 20 and set(value) <= PHONE_PATTERN_CHARS


def _validate_visit_form(form, today):
    """Return (errors, visit_day). `form` is a dict of stripped strings."""
    errors = {}

    if not form["full_name"]:
        errors["full_name"] = "Enter your full name."
    elif len(form["full_name"]) > 120:
        errors["full_name"] = "Name must be 120 characters or fewer."

    if not EMAIL_PATTERN.match(form["email"]) or len(form["email"]) > 120:
        errors["email"] = "Enter a valid email address."

    if not _valid_phone(form["phone"]):
        errors["phone"] = "Enter a phone number using digits, spaces, + or - (6 to 20 characters)."

    if form["purpose"] not in PURPOSES:
        errors["purpose"] = "Choose a purpose for your visit."

    if len(form["organization"]) > 120:
        errors["organization"] = "Organization must be 120 characters or fewer."
    if len(form["host_requested"]) > 120:
        errors["host_requested"] = "Host name must be 120 characters or fewer."
    if len(form["notes"]) > 1000:
        errors["notes"] = "Notes must be 1000 characters or fewer."

    visit_day = None
    try:
        visit_day = datetime.strptime(form["visit_date"], "%Y-%m-%d").date()
    except ValueError:
        errors["visit_date"] = "Choose the date of your visit."
    if visit_day:
        if visit_day < today:
            errors["visit_date"] = "The visit date cannot be in the past."
        elif visit_day > today + timedelta(days=MAX_DAYS_AHEAD):
            errors["visit_date"] = f"Requests can be made up to {MAX_DAYS_AHEAD} days ahead."

    return errors, visit_day


def _save_visit_request(form, visit_day, today):
    """Create the visitor (or reuse one with the same email) and a Pending request."""
    visitor = Visitor.query.filter_by(email=form["email"]).first()
    if visitor is None:
        visitor = Visitor(
            full_name=form["full_name"],
            email=form["email"],
            phone=form["phone"],
            organization=form["organization"] or None,
        )
        db.session.add(visitor)

    for _ in range(3):  # retry if two people get the same ID at the same moment
        visit = VisitRequest(
            request_id=generate_request_id(today),
            visitor=visitor,
            purpose=form["purpose"],
            host_requested=form["host_requested"] or None,
            visit_date=visit_day,
            notes=form["notes"] or None,
            status="Pending",
        )
        db.session.add(visit)
        try:
            db.session.commit()
            return visit
        except IntegrityError:
            db.session.rollback()
            visitor = Visitor.query.filter_by(email=form["email"]).first() or visitor
    return None


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/visit-request", methods=["GET", "POST"])
def visit_request():
    """Visitor registration + visit request. Saved with status Pending."""
    today = today_local()
    form = {key: request.form.get(key, "").strip() for key in FORM_FIELDS}
    form["email"] = form["email"].lower()
    errors = {}

    if request.method == "POST":
        errors, visit_day = _validate_visit_form(form, today)
        if not errors:
            visit = _save_visit_request(form, visit_day, today)
            if visit:
                return redirect(url_for("public.request_submitted", request_id=visit.request_id))
            flash("We could not save your request. Please try again.", "danger")
            return render_template("visit_request.html", form=form, errors=errors, purposes=PURPOSES, today=today), 500

    return (
        render_template("visit_request.html", form=form, errors=errors, purposes=PURPOSES, today=today),
        400 if errors else 200,
    )


@bp.route("/visit-request/<request_id>/submitted")
def request_submitted(request_id):
    # Shows only non-personal details, because request IDs are easy to guess.
    visit = VisitRequest.query.filter_by(request_id=request_id).first_or_404()
    return render_template("request_submitted.html", visit=visit)


@bp.route("/status", methods=["GET", "POST"])
def status():
    """Visitors look up their request with the request ID + the email they used."""
    form = {"request_id": "", "email": ""}
    visit = None
    status_code = 200

    if request.method == "POST":
        form["request_id"] = request.form.get("request_id", "").strip().upper()
        form["email"] = request.form.get("email", "").strip().lower()
        visit = VisitRequest.query.filter_by(request_id=form["request_id"]).first()
        # Same message for "wrong ID" and "wrong email" so IDs cannot be probed.
        if visit is None or visit.visitor.email != form["email"]:
            visit = None
            flash("We could not find a request with that ID and email.", "danger")
            status_code = 404

    return render_template("status.html", form=form, visit=visit), status_code


@bp.route("/pass/<code>")
def gate_pass(code):
    """The digital gate pass a visitor shows at the gate (printable)."""
    gate_pass = GatePass.query.filter_by(pass_code=code).first_or_404()
    return render_template("gate_pass.html", gate_pass=gate_pass, visit=gate_pass.visit_request)


@bp.route("/pass/<code>/qr.png")
def pass_qr(code):
    gate_pass = GatePass.query.filter_by(pass_code=code).first()
    if gate_pass is None:
        abort(404)
    return Response(
        qr_png(gate_pass.pass_code),
        mimetype="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
