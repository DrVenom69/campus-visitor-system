"""Visit history with search and filters. Hosts only see visits assigned to them."""
from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.constants import PER_PAGE, STATUSES
from app.models import HostAssignment, Visitor, VisitRequest
from app.utils import staff_required

bp = Blueprint("history", __name__, url_prefix="/history")


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _like_pattern(text):
    """Escape % and _ so the search box cannot be used as a wildcard."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@bp.route("/")
@staff_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    date_from = _parse_date(request.args.get("date_from", ""))
    date_to = _parse_date(request.args.get("date_to", ""))
    page = request.args.get("page", 1, type=int)

    query = VisitRequest.query.join(Visitor, VisitRequest.visitor_id == Visitor.id).options(
        joinedload(VisitRequest.visitor),
        joinedload(VisitRequest.host_assignment).joinedload(HostAssignment.host),
    )
    if current_user.role == "host":
        query = query.join(HostAssignment, HostAssignment.visit_request_id == VisitRequest.id).filter(
            HostAssignment.host_id == current_user.id
        )
    if q:
        pattern = _like_pattern(q)
        query = query.filter(
            or_(
                VisitRequest.request_id.ilike(pattern, escape="\\"),
                Visitor.full_name.ilike(pattern, escape="\\"),
                Visitor.email.ilike(pattern, escape="\\"),
            )
        )
    if status in STATUSES:
        query = query.filter(VisitRequest.status == status)
    if date_from:
        query = query.filter(VisitRequest.visit_date >= date_from)
    if date_to:
        query = query.filter(VisitRequest.visit_date <= date_to)

    pagination = query.order_by(VisitRequest.visit_date.desc(), VisitRequest.id.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )
    return render_template(
        "history/index.html",
        pagination=pagination,
        q=q,
        status=status,
        date_from=request.args.get("date_from", "") if date_from else "",
        date_to=request.args.get("date_to", "") if date_to else "",
        statuses=STATUSES,
    )
