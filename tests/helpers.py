"""Small builders shared by the tests."""
from datetime import timedelta

from app import db, services
from app.models import User, Visitor, VisitRequest
from app.utils import generate_request_id, today_local

PASSWORD = "test-pass-123"


def make_user(role, email=None, name=None, active=True):
    user = User(name=name or f"Test {role.title()}", email=email or f"{role}@campus.edu", role=role, is_active=active)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def make_visit(status="Pending", days=0, name="John Doe", email="john@example.com", host=None):
    """Create a visit request in the given status by running the real workflow."""
    visitor = Visitor.query.filter_by(email=email).first() or Visitor(
        full_name=name, email=email, phone="01700000000"
    )
    visit = VisitRequest(
        request_id=generate_request_id(),
        visitor=visitor,
        purpose="Meeting",
        visit_date=today_local() + timedelta(days=days),
        status="Pending",
    )
    db.session.add(visit)
    db.session.commit()
    if status == "Pending":
        return visit

    admin = User.query.filter_by(role="admin").first()
    guard = User.query.filter_by(role="security").first()
    if status == "Rejected":
        services.reject_request(visit, admin, "Not needed")
        return visit

    services.approve_request(visit, admin, host.id if host else None)
    if status == "Cancelled":
        services.cancel_request(visit, admin)
    if status in ("Checked In", "Checked Out", "Completed"):
        services.check_in(visit.gate_pass.pass_code, guard)
    if status in ("Checked Out", "Completed"):
        services.check_out(visit.gate_pass.pass_code, guard)
    if status == "Completed":
        services.complete_request(visit, admin)
    return visit


def login(client, email, password=PASSWORD, **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)
