"""Business rules for the visit workflow.

Routes call these functions; the functions change the database and raise
ServiceError when a rule is broken. The message is safe to show to the user.

Status flow: Pending -> Approved -> Checked In -> Checked Out -> Completed
             (or Rejected / Cancelled)
"""
from dataclasses import dataclass

from app import db
from app.models import CheckInOut, GatePass, HostAssignment, User
from app.utils import end_of_day_utc, today_local, utcnow


class ServiceError(Exception):
    """A business rule was broken. str(error) is a user-facing message."""


# ----------------------------------------------------------------------- helpers

def _get_host(host_id):
    try:
        host = User.query.filter_by(id=int(host_id), role="host", is_active=True).first()
    except (TypeError, ValueError):
        host = None
    if host is None:
        raise ServiceError("Choose a valid host.")
    return host


def _set_host(visit, host, actor):
    assignment = visit.host_assignment
    if assignment is None:
        visit.host_assignment = HostAssignment(host=host, assigned_by=actor)
    else:
        assignment.host = host
        assignment.assigned_by = actor
        assignment.assigned_at = utcnow()


def _fmt(day):
    return day.strftime("%d %b %Y")


# ------------------------------------------------------------- admin review actions

def approve_request(visit, admin, host_id=None):
    """Pending -> Approved. Creates the gate pass; optionally assigns a host."""
    if visit.status != "Pending":
        raise ServiceError("Only pending requests can be approved.")
    host = _get_host(host_id) if host_id else None

    visit.status = "Approved"
    visit.reviewed_by = admin
    visit.reviewed_at = utcnow()
    visit.rejection_reason = None
    if host:
        _set_host(visit, host, admin)
    visit.gate_pass = GatePass(valid_until=end_of_day_utc(visit.visit_date))
    db.session.commit()


def reject_request(visit, admin, reason):
    """Pending -> Rejected. A reason is required."""
    if visit.status != "Pending":
        raise ServiceError("Only pending requests can be rejected.")
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ServiceError("Enter a reason for rejecting this request.")
    if len(reason) > 500:
        raise ServiceError("The reason must be 500 characters or fewer.")

    visit.status = "Rejected"
    visit.rejection_reason = reason
    visit.reviewed_by = admin
    visit.reviewed_at = utcnow()
    db.session.commit()


def cancel_request(visit, actor):
    """Pending or Approved -> Cancelled. The gate pass stops working."""
    if visit.status not in ("Pending", "Approved"):
        raise ServiceError("Only pending or approved requests can be cancelled.")
    visit.status = "Cancelled"
    if visit.gate_pass:
        visit.gate_pass.is_active = False
    db.session.commit()


def assign_host(visit, admin, host_id):
    """Assign or change the host of an approved (or checked-in) visit."""
    if visit.status not in ("Approved", "Checked In"):
        raise ServiceError("A host can be assigned once a request is approved.")
    _set_host(visit, _get_host(host_id), admin)
    db.session.commit()


def complete_request(visit, admin):
    """Checked Out -> Completed (follow-up done)."""
    if visit.status != "Checked Out":
        raise ServiceError("Only visits that have checked out can be completed.")
    visit.status = "Completed"
    db.session.commit()


# --------------------------------------------------------------------- gate actions

@dataclass
class PassCheck:
    gate_pass: object = None
    visit: object = None
    action: str = None  # "check_in", "check_out" or None (blocked)
    message: str = ""


def evaluate_pass(code):
    """Look up a pass code and say what the guard may do with it."""
    code = (code or "").strip()
    gate_pass = GatePass.query.filter_by(pass_code=code).first() if code else None
    if gate_pass is None:
        return PassCheck(message="Pass code not found. Check the code and try again.")

    visit = gate_pass.visit_request
    status = visit.status

    if status == "Checked In":
        return PassCheck(gate_pass, visit, "check_out", "This visitor is inside the campus.")
    if status in ("Checked Out", "Completed"):
        return PassCheck(gate_pass, visit, None, "This pass was already used. The visitor has checked out.")
    if status == "Cancelled":
        return PassCheck(gate_pass, visit, None, "This visit was cancelled.")
    if status == "Rejected":
        return PassCheck(gate_pass, visit, None, "This visit was rejected.")
    if status != "Approved":
        return PassCheck(gate_pass, visit, None, "This visit has not been approved yet.")
    if not gate_pass.is_active:
        return PassCheck(gate_pass, visit, None, "This pass is no longer active.")

    today = today_local()
    if today < visit.visit_date:
        return PassCheck(gate_pass, visit, None, f"Too early. This pass is valid on {_fmt(visit.visit_date)}.")
    if today > visit.visit_date or (gate_pass.valid_until and utcnow() > gate_pass.valid_until):
        return PassCheck(gate_pass, visit, None, f"This pass has expired. It was valid on {_fmt(visit.visit_date)}.")
    return PassCheck(gate_pass, visit, "check_in", "This pass is valid.")


def check_in(code, guard):
    """Approved -> Checked In, if the pass is valid today."""
    check = evaluate_pass(code)
    if check.action != "check_in":
        raise ServiceError(check.message)

    db.session.add(CheckInOut(gate_pass=check.gate_pass, security=guard))
    check.visit.status = "Checked In"
    db.session.commit()
    return check.visit


def check_out(code, guard):
    """Checked In -> Checked Out. The pass is used up."""
    check = evaluate_pass(code)
    if check.action != "check_out":
        raise ServiceError(check.message)

    open_record = (
        CheckInOut.query.filter_by(gate_pass_id=check.gate_pass.id, check_out_time=None)
        .order_by(CheckInOut.id.desc())
        .first()
    )
    if open_record is None:
        raise ServiceError("No open check-in was found for this pass.")

    open_record.check_out_time = utcnow()
    check.visit.status = "Checked Out"
    check.gate_pass.is_active = False
    db.session.commit()
    return check.visit
