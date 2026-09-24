"""Staff dashboard: live numbers and the latest visit requests."""
from flask import Blueprint, render_template
from sqlalchemy.orm import joinedload

from app.models import HostAssignment, Visitor, VisitRequest
from app.utils import staff_required, today_local

bp = Blueprint("dashboard", __name__)


def initials(name):
    return "".join(part[0] for part in name.split()[:2]).upper() or "?"


def host_label(visit):
    """Assigned host, else the person the visitor asked for, else 'Not assigned'."""
    if visit.host_assignment:
        return visit.host_assignment.host.name
    return visit.host_requested or "Not assigned"


@bp.route("/dashboard")
@staff_required
def index():
    today = today_local()

    stats = {
        "total_visitors": Visitor.query.count(),
        "pending": VisitRequest.query.filter_by(status="Pending").count(),
        "inside": VisitRequest.query.filter_by(status="Checked In").count(),
        "today": VisitRequest.query.filter_by(visit_date=today).count(),
        "approved_today": VisitRequest.query.filter(
            VisitRequest.visit_date == today,
            VisitRequest.status.in_(["Approved", "Checked In", "Checked Out", "Completed"]),
        ).count(),
    }

    latest = (
        VisitRequest.query.options(
            joinedload(VisitRequest.visitor),
            joinedload(VisitRequest.host_assignment).joinedload(HostAssignment.host),
        )
        .order_by(VisitRequest.created_at.desc(), VisitRequest.id.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_visits=[
            {
                "request_id": visit.request_id,
                "name": visit.visitor.full_name,
                "initials": initials(visit.visitor.full_name),
                "email": visit.visitor.email,
                "purpose": visit.purpose,
                "host": host_label(visit),
                "visit_date": visit.visit_date.strftime("%d %b %Y"),
                "status": visit.status,
            }
            for visit in latest
        ],
    )
