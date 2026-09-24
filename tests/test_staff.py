"""Login, permissions, dashboard, admin queue, gate, history and users."""
from datetime import timedelta

import pytest

from app import db
from app.models import CheckInOut, User, VisitRequest
from app.utils import today_local
from tests.helpers import PASSWORD, login, make_user, make_visit


def host():
    return User.query.filter_by(role="host").first()


# ------------------------------------------------------------------------------- auth

def test_login_and_logout(client):
    assert login(client, "admin@campus.edu").status_code == 302
    page = client.get("/dashboard")
    assert page.status_code == 200 and b"Welcome back, Test Admin" in page.data
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_wrong_password_and_unknown_user(client):
    for email, password in (("admin@campus.edu", "wrong"), ("nobody@campus.edu", PASSWORD)):
        response = login(client, email, password)
        assert response.status_code == 401 and b"incorrect" in response.data


def test_deactivated_user_cannot_log_in(app, client):
    make_user("admin", email="gone@campus.edu", active=False)
    assert login(client, "gone@campus.edu").status_code == 401


def test_login_will_not_redirect_off_site(client):
    for target in ("https://evil.example.com", "//evil.example.com", "/\\evil.example.com"):
        response = client.post(f"/login?next={target}", data={"email": "admin@campus.edu", "password": PASSWORD})
        assert response.headers["Location"].endswith("/dashboard")


def test_login_returns_to_the_page_that_was_asked_for(client):
    response = client.get("/users/")
    assert "/login?next=" in response.headers["Location"]
    response = client.post(response.headers["Location"], data={"email": "admin@campus.edu", "password": PASSWORD})
    assert response.headers["Location"].endswith("/users/")


def test_logout_needs_post(client):
    assert client.get("/logout").status_code == 405


# --------------------------------------------------------------------- who may open what

# url -> roles that get 200 (everyone else gets 403)
PERMISSIONS = {
    "/dashboard": {"admin", "host", "security"},
    "/history/": {"admin", "host", "security"},
    "/requests/": {"admin"},
    "/users/": {"admin"},
    "/users/new": {"admin"},
    "/gate/": {"admin", "security"},
    "/gate/inside": {"admin", "security"},
}


@pytest.mark.parametrize("url", sorted(PERMISSIONS))
@pytest.mark.parametrize("role", ["admin", "host", "security", "visitor"])
def test_permission_matrix(as_role, url, role):
    expected = 200 if role in PERMISSIONS[url] else 403
    assert as_role(role).get(url).status_code == expected


@pytest.mark.parametrize("url", sorted(PERMISSIONS))
def test_anonymous_is_sent_to_login(client, url):
    response = client.get(url)
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_only_admin_can_post_admin_actions(as_role):
    visit = make_visit()
    for role in ("host", "security", "visitor"):
        client = as_role(role)
        for action in ("approve", "reject", "cancel", "assign-host", "complete"):
            assert client.post(f"/requests/{visit.request_id}/{action}").status_code == 403
    assert db.session.get(VisitRequest, visit.id).status == "Pending"


# ------------------------------------------------------------------------- dashboard

def test_dashboard_empty_state_and_links(as_role):
    page = as_role("admin").get("/dashboard")
    assert b"No visit requests yet." in page.data and b"All caught up" in page.data
    assert b"/requests/" in page.data and b"/users/" in page.data


def test_dashboard_stats(as_role):
    make_visit("Pending", email="a@x.com")
    make_visit("Approved", email="b@x.com")
    make_visit("Checked In", email="c@x.com")
    make_visit("Approved", days=3, email="d@x.com")
    page = as_role("admin").get("/dashboard")
    assert b"status-badge pending" in page.data and b"status-badge checked-in" in page.data
    assert b"Requires attention" in page.data
    assert b">4</strong>" in page.data  # total visitors


def test_sidebar_matches_role(as_role):
    admin_page = as_role("admin").get("/dashboard").data
    guard_page = as_role("security").get("/dashboard").data
    host_page = as_role("host").get("/dashboard").data
    assert b"/users/" in admin_page and b"/users/" not in guard_page
    assert b"/gate/" in guard_page and b"/gate/" not in host_page
    assert b"/requests/" not in guard_page and b"/requests/" not in host_page


def test_pending_count_badge_for_admin(as_role):
    make_visit()
    assert b'class="nav-count">1<' in as_role("admin").get("/dashboard").data


# --------------------------------------------------------------------- admin requests

def test_requests_queue_defaults_to_pending(as_role):
    pending = make_visit("Pending", email="p@x.com", name="Pending Person")
    make_visit("Approved", email="a@x.com", name="Approved Person")
    page = as_role("admin").get("/requests/")
    assert pending.request_id.encode() in page.data
    assert b"Pending Person" in page.data and b"Approved Person" not in page.data


def test_requests_status_tabs_and_bad_status(as_role):
    make_visit("Approved", name="Approved Person")
    client = as_role("admin")
    assert b"Approved Person" in client.get("/requests/?status=Approved").data
    assert b"Approved Person" in client.get("/requests/?status=All").data
    assert b"Approved Person" not in client.get("/requests/?status=nonsense").data  # falls back to Pending


def test_request_detail_and_404(as_role):
    visit = make_visit()
    client = as_role("admin")
    page = client.get(f"/requests/{visit.request_id}")
    assert page.status_code == 200 and b"Approve request" in page.data and b"Reject request" in page.data
    assert client.get("/requests/VR-nope").status_code == 404


def test_admin_approves_with_host(as_role):
    visit = make_visit()
    client = as_role("admin")
    response = client.post(f"/requests/{visit.request_id}/approve", data={"host_id": host().id}, follow_redirects=True)
    assert b"Request approved" in response.data
    visit = db.session.get(VisitRequest, visit.id)
    assert visit.status == "Approved" and visit.host_assignment.host == host() and visit.gate_pass
    assert visit.gate_pass.pass_code.encode() in client.get(f"/requests/{visit.request_id}").data


def test_admin_approves_without_host(as_role):
    visit = make_visit()
    as_role("admin").post(f"/requests/{visit.request_id}/approve", data={"host_id": ""})
    assert db.session.get(VisitRequest, visit.id).status == "Approved"


def test_admin_reject_needs_a_reason(as_role):
    visit = make_visit()
    client = as_role("admin")
    response = client.post(f"/requests/{visit.request_id}/reject", data={"reason": ""}, follow_redirects=True)
    assert b"Enter a reason" in response.data
    assert db.session.get(VisitRequest, visit.id).status == "Pending"

    client.post(f"/requests/{visit.request_id}/reject", data={"reason": "Fully booked"})
    visit = db.session.get(VisitRequest, visit.id)
    assert visit.status == "Rejected" and visit.rejection_reason == "Fully booked"


def test_admin_cancels_and_assigns_and_completes(as_role):
    client = as_role("admin")

    approved = make_visit("Approved", email="a@x.com")
    client.post(f"/requests/{approved.request_id}/assign-host", data={"host_id": host().id})
    assert db.session.get(VisitRequest, approved.id).host_assignment.host == host()
    client.post(f"/requests/{approved.request_id}/cancel")
    assert db.session.get(VisitRequest, approved.id).status == "Cancelled"

    done = make_visit("Checked Out", email="b@x.com")
    client.post(f"/requests/{done.request_id}/complete")
    assert db.session.get(VisitRequest, done.id).status == "Completed"


def test_invalid_transition_shows_error_not_crash(as_role):
    visit = make_visit("Approved")
    response = as_role("admin").post(f"/requests/{visit.request_id}/approve", follow_redirects=True)
    assert response.status_code == 200 and b"Only pending requests can be approved" in response.data


# ------------------------------------------------------------------------------- gate

def lookup(client, code):
    return client.post("/gate/", data={"pass_code": code})


def test_gate_lookup_valid_pass(as_role):
    visit = make_visit("Approved", host=host())
    page = lookup(as_role("security"), visit.gate_pass.pass_code)
    assert b"Ready to check in" in page.data and b"John Doe" in page.data and b"Dr. Host" in page.data


@pytest.mark.parametrize("status, expected", [
    ("Cancelled", b"cancelled"),
    ("Checked Out", b"already used"),
])
def test_gate_lookup_blocked_passes(as_role, status, expected):
    visit = make_visit(status)
    page = lookup(as_role("security"), visit.gate_pass.pass_code)
    assert b"Cannot let this visitor in" in page.data and expected in page.data
    assert b"btn-block" not in page.data  # no action button is offered


def test_gate_lookup_future_and_unknown(as_role):
    client = as_role("security")
    future = make_visit("Approved", days=1)
    assert b"Too early" in lookup(client, future.gate_pass.pass_code).data
    assert b"not found" in lookup(client, "garbage").data


def test_guard_checks_visitor_in_and_out(as_role):
    visit = make_visit("Approved")
    code = visit.gate_pass.pass_code
    guard = as_role("security")

    response = guard.post("/gate/check-in", data={"pass_code": code}, follow_redirects=True)
    assert b"Checked in: John Doe" in response.data
    assert db.session.get(VisitRequest, visit.id).status == "Checked In"
    assert CheckInOut.query.one().security.role == "security"

    assert b"Ready to check out" in lookup(guard, code).data
    inside = guard.get("/gate/inside")
    assert b"John Doe" in inside.data and b"1 visitor" in inside.data

    response = guard.post("/gate/check-out", data={"pass_code": code}, follow_redirects=True)
    assert b"Checked out: John Doe" in response.data
    assert db.session.get(VisitRequest, visit.id).status == "Checked Out"
    assert b"Nobody is inside" in guard.get("/gate/inside").data


def test_check_in_twice_and_bad_codes_show_errors(as_role):
    visit = make_visit("Checked In")
    guard = as_role("security")
    response = guard.post("/gate/check-in", data={"pass_code": visit.gate_pass.pass_code}, follow_redirects=True)
    assert b"inside the campus" in response.data
    response = guard.post("/gate/check-in", data={"pass_code": "nope"}, follow_redirects=True)
    assert b"not found" in response.data
    assert CheckInOut.query.count() == 1


def test_inside_page_check_out_button(as_role):
    visit = make_visit("Checked In")
    guard = as_role("security")
    assert b"Check out" in guard.get("/gate/inside").data
    guard.post("/gate/check-out", data={"pass_code": visit.gate_pass.pass_code})
    assert db.session.get(VisitRequest, visit.id).status == "Checked Out"


def test_hosts_and_visitors_cannot_use_the_gate(as_role):
    visit = make_visit("Approved")
    for role in ("host", "visitor"):
        client = as_role(role)
        assert client.post("/gate/check-in", data={"pass_code": visit.gate_pass.pass_code}).status_code == 403
    assert db.session.get(VisitRequest, visit.id).status == "Approved"


# ---------------------------------------------------------------------------- history

def test_history_search_and_filters(as_role):
    a = make_visit("Approved", name="Alice Smith", email="alice@x.com")
    make_visit("Pending", name="Bob Jones", email="bob@x.com", days=5)
    client = as_role("admin")

    assert b"Alice Smith" in client.get("/history/?q=alice").data
    assert b"Bob Jones" not in client.get("/history/?q=alice").data
    assert b"Alice Smith" in client.get(f"/history/?q={a.request_id}").data
    assert b"Bob Jones" in client.get("/history/?q=bob@x").data
    assert b"Bob Jones" not in client.get("/history/?status=Approved").data
    assert b"Bob Jones" in client.get("/history/?status=Pending").data

    today = today_local()
    only_future = client.get(f"/history/?date_from={today + timedelta(days=3)}").data
    assert b"Bob Jones" in only_future and b"Alice Smith" not in only_future
    only_today = client.get(f"/history/?date_to={today}").data
    assert b"Alice Smith" in only_today and b"Bob Jones" not in only_today


def test_history_search_treats_percent_literally(as_role):
    make_visit(name="Alice Smith", email="alice@x.com")
    page = as_role("admin").get("/history/?q=%25")
    assert b"No visits match these filters." in page.data


def test_history_ignores_garbage_filters(as_role):
    make_visit()
    page = as_role("admin").get("/history/?status=bogus&date_from=xx&page=abc")
    assert page.status_code == 200 and b"John Doe" in page.data


def test_history_paginates(as_role):
    for i in range(17):
        make_visit(name=f"Person {i:02d}", email=f"p{i}@x.com")
    client = as_role("admin")
    first = client.get("/history/")
    assert b"Page 1 of 2" in first.data and b"page=2" in first.data
    second = client.get("/history/?page=2")
    assert b"Page 2 of 2" in second.data
    assert client.get("/history/?page=99").status_code == 200  # out of range is empty, not an error


def test_host_sees_only_own_visitors(as_role):
    make_visit("Approved", name="Mine Visitor", email="m@x.com", host=host())
    make_visit("Approved", name="Not Mine", email="n@x.com")
    page = as_role("host").get("/history/")
    assert b"Mine Visitor" in page.data and b"Not Mine" not in page.data
    assert b"/requests/VR" not in page.data  # no link into the admin pages


# ------------------------------------------------------------------------------ users

def new_user_form(**overrides):
    data = {"name": "Nina Guard", "email": "Nina@Campus.edu", "role": "security", "password": "longenough1"}
    data.update(overrides)
    return data


def test_admin_creates_user_who_can_log_in(as_role, app):
    response = as_role("admin").post("/users/new", data=new_user_form(), follow_redirects=True)
    assert b"Account created for Nina Guard" in response.data
    user = User.query.filter_by(email="nina@campus.edu").one()
    assert user.role == "security" and user.password_hash != "longenough1"
    assert login(app.test_client(), "nina@campus.edu", "longenough1").status_code == 302


@pytest.mark.parametrize("overrides", [
    {"name": ""},
    {"email": "bad"},
    {"email": "admin@campus.edu"},   # already exists
    {"role": "visitor"},
    {"role": "superuser"},
    {"password": "short"},
])
def test_create_user_validation(as_role, overrides):
    before = User.query.count()
    response = as_role("admin").post("/users/new", data=new_user_form(**overrides))
    assert response.status_code == 400 and b"field-error" in response.data
    assert User.query.count() == before


def test_admin_can_deactivate_but_not_self(as_role, app):
    client = as_role("admin")
    guard = User.query.filter_by(role="security").one()
    client.post(f"/users/{guard.id}/toggle")
    assert not db.session.get(User, guard.id).is_active
    assert login(app.test_client(), "security@campus.edu").status_code == 401
    client.post(f"/users/{guard.id}/toggle")
    assert db.session.get(User, guard.id).is_active

    me = User.query.filter_by(role="admin").one()
    response = client.post(f"/users/{me.id}/toggle", follow_redirects=True)
    assert b"cannot deactivate your own" in response.data and db.session.get(User, me.id).is_active


def test_user_menu_opens_profile(as_role):
    page = as_role("admin").get("/dashboard")
    assert b"My profile" in page.data and b"/users/profile" in page.data


def test_staff_can_update_profile(as_role, app):
    client = as_role("admin")
    response = client.post(
        "/users/profile",
        data={"name": "Updated Admin", "email": "updated@campus.edu"},
        follow_redirects=True,
    )
    assert response.status_code == 200 and b"profile has been updated" in response.data
    user = User.query.filter_by(email="updated@campus.edu").one()
    assert user.name == "Updated Admin"
    assert b"Updated Admin" in client.get("/users/profile").data

    assert login(app.test_client(), "updated@campus.edu").status_code == 302


def test_profile_rejects_duplicate_email(as_role):
    client = as_role("admin")
    response = client.post(
        "/users/profile",
        data={"name": "Test Admin", "email": "host@campus.edu"},
    )
    assert response.status_code == 400 and b"already exists" in response.data


def test_staff_can_change_password(as_role, app):
    client = as_role("admin")
    response = client.post(
        "/users/profile/password",
        data={
            "current_password": PASSWORD,
            "new_password": "new-secure-password",
            "confirm_password": "new-secure-password",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200 and b"password has been changed" in response.data
    assert login(app.test_client(), "admin@campus.edu", PASSWORD).status_code == 401
    assert login(app.test_client(), "admin@campus.edu", "new-secure-password").status_code == 302


def test_password_change_validates_current_and_confirmation(as_role):
    client = as_role("admin")
    response = client.post(
        "/users/profile/password",
        data={
            "current_password": "wrong-password",
            "new_password": "new-secure-password",
            "confirm_password": "different-password",
        },
    )
    assert response.status_code == 400
    assert b"current password is incorrect" in response.data
    assert b"Passwords do not match" in response.data


def test_toggle_unknown_user_is_404(as_role):
    assert as_role("admin").post("/users/9999/toggle").status_code == 404
