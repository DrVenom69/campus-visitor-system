import csv
import io

from app import db
from app.models import User
from tests.helpers import make_visit


def test_history_export_includes_filtered_visit_data_and_safe_values(as_role):
    visit = make_visit("Checked Out", name="=Formula", email="+8801700000000")
    make_visit("Pending", name="Filtered Out", email="filtered@example.com")
    visit.visitor.phone = "+8801800000000"
    visit.visitor.organization = "Campus"
    visit.host_requested = "Dr. Requested"
    db.session.commit()
    client = as_role("admin")

    response = client.get("/history/export.csv?status=Checked+Out")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment; filename=visits-" in response.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "Request ID", "Visitor name", "Email", "Phone", "Organization", "Purpose",
        "Visit date", "Host", "Status", "Submitted at", "Checked in", "Checked out",
    ]
    assert rows[1][0] == visit.request_id
    assert rows[1][1] == "'=Formula"
    assert rows[1][2] == "'+8801700000000"
    assert rows[1][3] == "'+8801800000000"
    assert rows[1][7] == "Dr. Requested"
    assert rows[1][8] == "Checked Out"
    assert rows[1][10] and rows[1][11]


def test_history_export_requires_staff_and_applies_host_scope(as_role, client):
    mine = make_visit(
        "Approved",
        name="Assigned Visitor",
        email="assigned@example.com",
        host=User.query.filter_by(email="host@campus.edu").one(),
    )
    make_visit(name="Public Visitor", email="public@example.com")
    assert client.get("/history/export.csv").status_code == 302
    assert as_role("visitor").get("/history/export.csv").status_code == 403
    response = as_role("host").get("/history/export.csv")
    assert response.status_code == 200
    assert mine.request_id.encode() in response.data
    assert b"Public Visitor" not in response.data