"""Visit history with search and filters. Hosts only see visits assigned to them."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.constants import PER_PAGE, STATUSES
from app.models import GatePass, HostAssignment, Visitor, VisitRequest
from app.utils import staff_required, to_local

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


def build_history_query(args):
    q = args.get("q", "").strip()
    status = args.get("status", "")
    date_from = _parse_date(args.get("date_from", ""))
    date_to = _parse_date(args.get("date_to", ""))

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

    return query, {
        "q": q,
        "status": status,
        "date_from": args.get("date_from", "") if date_from else "",
        "date_to": args.get("date_to", "") if date_to else "",
    }


@bp.route("/")
@staff_required
def index():
    query, filters = build_history_query(request.args)
    page = request.args.get("page", 1, type=int)

    pagination = query.order_by(VisitRequest.visit_date.desc(), VisitRequest.id.desc()).paginate(
        page=page, per_page=PER_PAGE, error_out=False
    )
    return render_template(
        "history/index.html",
        pagination=pagination,
        **filters,
        statuses=STATUSES,
    )



CSV_COLUMNS = [
    "Request ID", "Visitor name", "Email", "Phone", "Organization", "Purpose",
    "Visit date", "Host", "Status", "Submitted at", "Checked in", "Checked out",
]


def _csv_safe(value):
    """Stop Excel running visitor-typed text as a formula."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _fmt_time(value):
    local = to_local(value)
    return local.strftime("%Y-%m-%d %H:%M") if local else ""


@bp.route("/export.csv")
@staff_required
def export():
    query, _filters = build_history_query(request.args)
    visits = query.options(
        joinedload(VisitRequest.gate_pass).joinedload(GatePass.check_ins)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)

    for visit in visits:
        if visit.host_assignment:
            host = visit.host_assignment.host.name
        else:
            host = visit.host_requested or ""

        check_in = check_out = None
        if visit.gate_pass and visit.gate_pass.check_ins:
            latest = max(visit.gate_pass.check_ins, key=lambda c: c.check_in_time)
            check_in, check_out = latest.check_in_time, latest.check_out_time

        writer.writerow([
            _csv_safe(value)
            for value in (
                visit.request_id,
                visit.visitor.full_name,
                visit.visitor.email,
                visit.visitor.phone,
                visit.visitor.organization,
                visit.purpose,
                visit.visit_date.strftime("%Y-%m-%d"),
                host,
                visit.status,
                _fmt_time(visit.created_at),
                _fmt_time(check_in),
                _fmt_time(check_out),
            )
        ])

    filename = f"visits-{datetime.now():%Y%m%d}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )