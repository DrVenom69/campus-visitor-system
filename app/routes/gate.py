"""Security gate: look up a pass (typed code or camera scan), check in, check out."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.models import CheckInOut, GatePass, VisitRequest
from app.services import ServiceError, check_in, check_out, evaluate_pass
from app.utils import roles_required, utcnow

bp = Blueprint("gate", __name__, url_prefix="/gate")
gate_staff = roles_required("admin", "security")


@bp.route("/", methods=["GET", "POST"])
@gate_staff
def index():
    """Step 1: the guard scans or types a code. Step 2: they confirm the action."""
    code, check = "", None
    if request.method == "POST":
        code = request.form.get("pass_code", "").strip()
        check = evaluate_pass(code)

    recent = (
        CheckInOut.query.options(joinedload(CheckInOut.gate_pass).joinedload(GatePass.visit_request))
        .order_by(CheckInOut.id.desc())
        .limit(6)
        .all()
    )
    return render_template("gate/index.html", code=code, check=check, recent=recent)


def _gate_action(action, success_message):
    code = request.form.get("pass_code", "")
    try:
        visit = action(code, current_user._get_current_object())
        flash(f"{success_message}: {visit.visitor.full_name} ({visit.request_id}).", "success")
    except ServiceError as error:
        flash(str(error), "danger")
    return redirect(url_for("gate.index"))


@bp.route("/check-in", methods=["POST"])
@gate_staff
def do_check_in():
    return _gate_action(check_in, "Checked in")


@bp.route("/check-out", methods=["POST"])
@gate_staff
def do_check_out():
    return _gate_action(check_out, "Checked out")


@bp.route("/inside")
@gate_staff
def inside():
    """Everyone who is checked in and has not checked out yet."""
    open_records = (
        CheckInOut.query.filter(CheckInOut.check_out_time.is_(None))
        .join(GatePass, CheckInOut.gate_pass_id == GatePass.id)
        .join(VisitRequest, GatePass.visit_request_id == VisitRequest.id)
        .filter(VisitRequest.status == "Checked In")
        .options(joinedload(CheckInOut.gate_pass).joinedload(GatePass.visit_request))
        .order_by(CheckInOut.check_in_time)
        .all()
    )
    return render_template("gate/inside.html", records=open_records, now=utcnow())
