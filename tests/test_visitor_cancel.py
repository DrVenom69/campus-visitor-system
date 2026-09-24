from app import db, services
from app.models import VisitRequest
from tests.helpers import make_visit


def cancel(client, visit, email=None):
    return client.post(
        "/status/cancel",
        data={"request_id": visit.request_id, "email": email or visit.visitor.email},
    )


def test_visitor_can_cancel_pending_request(client):
    visit = make_visit()

    response = cancel(client, visit)

    assert response.status_code == 200
    assert b"request has been cancelled" in response.data
    assert db.session.get(VisitRequest, visit.id).status == "Cancelled"


def test_visitor_can_cancel_approved_request_and_disable_pass(client):
    visit = make_visit("Approved")

    response = cancel(client, visit)

    assert response.status_code == 200
    assert visit.status == "Cancelled" and not visit.gate_pass.is_active
    assert services.evaluate_pass(visit.gate_pass.pass_code).message == "This visit was cancelled."


def test_cancel_requires_matching_email(client):
    visit = make_visit()

    response = cancel(client, visit, email="wrong@example.com")

    assert response.status_code == 404
    assert visit.status == "Pending"


def test_checked_in_request_cannot_be_cancelled(client):
    visit = make_visit("Checked In")

    response = cancel(client, visit)

    assert response.status_code == 400
    assert b"Only pending or approved requests can be cancelled" in response.data
    assert visit.status == "Checked In"