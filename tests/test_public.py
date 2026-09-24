import re
from datetime import timedelta

import pytest

from app.models import Visitor, VisitRequest
from app.utils import today_local
from tests.helpers import make_visit


def valid_form(**overrides):
    data = {
        "full_name": "John Doe",
        "email": "John@Example.com",
        "phone": "+880 1700-000000",
        "organization": "Acme Ltd",
        "purpose": "Meeting",
        "host_requested": "Dr. Smith",
        "visit_date": (today_local() + timedelta(days=2)).isoformat(),
        "notes": "",
    }
    data.update(overrides)
    return data


def test_public_pages_load(client):
    for path in ("/", "/visit-request", "/login", "/status"):
        assert client.get(path).status_code == 200


def test_unknown_page_is_404(client):
    assert client.get("/nope").status_code == 404


def test_visit_request_is_saved_as_pending(client, app):
    response = client.post("/visit-request", data=valid_form())
    assert response.status_code == 302

    visit = VisitRequest.query.one()
    assert re.fullmatch(r"VR-\d{8}-0001", visit.request_id)
    assert visit.status == "Pending"
    assert visit.visitor.email == "john@example.com"  # lower-cased
    assert visit.host_requested == "Dr. Smith"

    page = client.get(response.headers["Location"])
    assert page.status_code == 200 and visit.request_id.encode() in page.data


def test_request_ids_count_up_and_visitors_are_reused(client):
    client.post("/visit-request", data=valid_form())
    client.post("/visit-request", data=valid_form(purpose="Delivery"))
    ids = [v.request_id for v in VisitRequest.query.order_by(VisitRequest.id)]
    assert ids[0].endswith("-0001") and ids[1].endswith("-0002")
    assert Visitor.query.count() == 1


@pytest.mark.parametrize("field, value", [
    ("full_name", ""),
    ("full_name", "x" * 121),
    ("email", "not-an-email"),
    ("phone", "abc"),
    ("phone", "12"),
    ("purpose", "Hacking"),
    ("visit_date", "yesterday"),
    ("visit_date", ""),
    ("visit_date", lambda: (today_local() - timedelta(days=1)).isoformat()),
    ("visit_date", lambda: (today_local() + timedelta(days=400)).isoformat()),
    ("notes", "n" * 1001),
])
def test_invalid_visit_requests_are_rejected(client, field, value):
    if callable(value):  # dates need the app timezone, so they are built inside the test
        value = value()
    response = client.post("/visit-request", data=valid_form(**{field: value}))
    assert response.status_code == 400
    assert b"is-invalid" in response.data
    assert VisitRequest.query.count() == 0


def test_form_keeps_what_the_visitor_typed(client):
    response = client.post("/visit-request", data=valid_form(email="bad", full_name="Keep Me"))
    assert b"Keep Me" in response.data


def test_submitted_page_for_unknown_id_is_404(client):
    assert client.get("/visit-request/VR-00000000-0000/submitted").status_code == 404


# -------------------------------------------------------------------- status lookup

def lookup(client, visit, email=None):
    return client.post("/status", data={"request_id": visit.request_id, "email": email or visit.visitor.email})


def test_status_lookup_pending(client):
    response = lookup(client, make_visit())
    assert response.status_code == 200 and b"waiting for review" in response.data
    assert b"/pass/" not in response.data


def test_status_lookup_is_case_insensitive(client):
    visit = make_visit()
    response = client.post("/status", data={"request_id": visit.request_id.lower(), "email": " JOHN@example.com "})
    assert response.status_code == 200 and b"waiting for review" in response.data


def test_status_lookup_needs_matching_email(client):
    visit = make_visit()
    wrong_email = lookup(client, visit, email="someone@else.com")
    unknown_id = client.post("/status", data={"request_id": "VR-00000000-0000", "email": "john@example.com"})
    assert wrong_email.status_code == unknown_id.status_code == 404
    assert b"could not find" in wrong_email.data and b"could not find" in unknown_id.data


def test_status_lookup_rejected_shows_reason(client):
    response = lookup(client, make_visit("Rejected"))
    assert b"Not needed" in response.data


def test_status_lookup_approved_links_to_pass(client):
    visit = make_visit("Approved")
    response = lookup(client, visit)
    assert f"/pass/{visit.gate_pass.pass_code}".encode() in response.data


def test_status_lookup_cancelled_has_no_pass_link(client):
    response = lookup(client, make_visit("Cancelled"))
    assert b"cancelled" in response.data and b"/pass/" not in response.data


# ---------------------------------------------------------------------- gate pass page

def test_gate_pass_page_and_qr_image(client):
    visit = make_visit("Approved")
    code = visit.gate_pass.pass_code

    page = client.get(f"/pass/{code}")
    assert page.status_code == 200
    assert visit.request_id.encode() in page.data and b"John Doe" in page.data
    assert f"/pass/{code}/qr.png".encode() in page.data

    image = client.get(f"/pass/{code}/qr.png")
    assert image.status_code == 200 and image.mimetype == "image/png"
    assert image.data.startswith(b"\x89PNG\r\n\x1a\n")


def test_unknown_pass_code_is_404(client):
    assert client.get("/pass/not-a-real-code").status_code == 404
    assert client.get("/pass/not-a-real-code/qr.png").status_code == 404


def test_inactive_pass_is_marked_not_active(client):
    visit = make_visit("Cancelled")
    page = client.get(f"/pass/{visit.gate_pass.pass_code}")
    assert page.status_code == 200 and b"not active" in page.data


def test_qr_encodes_the_pass_code(app):
    """Round-trip: the QR image must contain exactly the pass code."""
    from app.qr import qr_png
    import io
    from PIL import Image

    try:
        import cv2  # optional, only used if installed
        import numpy as np
    except ImportError:
        pytest.skip("opencv not installed; QR decode round-trip skipped")

    code = make_visit("Approved").gate_pass.pass_code
    image = np.array(Image.open(io.BytesIO(qr_png(code))).convert("RGB"))
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    assert decoded == code
