"""Admin work queue: review, approve / reject, assign host, cancel, complete."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.constants import PER_PAGE, STATUSES
from app.models import HostAssignment, User, VisitRequest
from app.services import (
    ServiceError,
    approve_request,
    assign_host,
    cancel_request,
    complete_request,
    reject_request,
)
from app.utils import roles_required

bp = Blueprint("requests", __name__, url_prefix="/requests")
admin_only = roles_required("admin")


@bp.route("/")
@admin_only
def index():
    status = request.args.get("status", "Pending")
    if status != "All" and status not in STATUSES:
        status = "Pending"
    page = request.args.get("page", 1, type=int)

    query = VisitRequest.query.options(
        joinedload(VisitRequest.visitor),
        joinedload(VisitRequest.host_assignment).joinedload(HostAssignment.host),
    )
    if status != "All":
        query = query.filter(VisitRequest.status == status)
    pagination = query.order_by(VisitRequest.created_at.desc(), VisitRequest.id.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )

    counts = dict(
        db.session.query(VisitRequest.status, func.count(VisitRequest.id)).group_by(VisitRequest.status).all()
    )
    return render_template(
        "requests/list.html",
        pagination=pagination,
        status=status,
        counts=counts,
        total=sum(counts.values()),
        statuses=STATUSES,
    )


@bp.route("/<request_id>")
@admin_only
def detail(request_id):
    visit = VisitRequest.query.filter_by(request_id=request_id).first_or_404()
    hosts = User.query.filter_by(role="host", is_active=True).order_by(User.name).all()
    check_ins = visit.gate_pass.check_ins if visit.gate_pass else []
    return render_template("requests/detail.html", visit=visit, hosts=hosts, check_ins=check_ins)


def _run(request_id, action, success_message, *args):
    """Load the request, run a service action, and flash the result."""
    visit = VisitRequest.query.filter_by(request_id=request_id).first_or_404()
    try:
        action(visit, current_user._get_current_object(), *args)
        flash(success_message, "success")
    except ServiceError as error:
        flash(str(error), "danger")
    return redirect(url_for("requests.detail", request_id=request_id))


@bp.route("/<request_id>/approve", methods=["POST"])
@admin_only
def approve(request_id):
    return _run(request_id, approve_request, "Request approved. The gate pass is ready.",
                request.form.get("host_id") or None)


@bp.route("/<request_id>/reject", methods=["POST"])
@admin_only
def reject(request_id):
    return _run(request_id, reject_request, "Request rejected.", request.form.get("reason", ""))


@bp.route("/<request_id>/cancel", methods=["POST"])
@admin_only
def cancel(request_id):
    return _run(request_id, cancel_request, "Request cancelled.")


@bp.route("/<request_id>/assign-host", methods=["POST"])
@admin_only
def assign_host_route(request_id):
    return _run(request_id, assign_host, "Host assigned.", request.form.get("host_id"))


@bp.route("/<request_id>/complete", methods=["POST"])
@admin_only
def complete(request_id):
    return _run(request_id, complete_request, "Visit marked as completed.")
