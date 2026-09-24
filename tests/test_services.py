from datetime import date, timedelta

import pytest

from app import db, services
from app.models import CheckInOut, HostAssignment, User
from app.services import ServiceError
from app.utils import end_of_day_utc, utcnow
from tests.helpers import make_user, make_visit



def admin():
    return User.query.filter_by(role="admin").first()


def guard():
    return User.query.filter_by(role="security").first()


def host():
    return User.query.filter_by(role="host").first()


# ------------------------------------------------------------------ approve / reject

def test_approve_creates_pass_and_host(app):
    visit = make_visit()
    services.approve_request(visit, admin(), host().id)
    assert visit.status == "Approved"
    assert visit.reviewed_by == admin() and visit.reviewed_at
    assert visit.host_assignment.host == host()
    assert len(visit.gate_pass.pass_code) >= 32
    assert visit.gate_pass.valid_until == end_of_day_utc(visit.visit_date)


def test_approve_without_host_is_allowed(app):
    visit = make_visit("Approved")
    assert visit.host_assignment is None and visit.gate_pass


def test_pass_codes_are_unique(app):
    codes = {make_visit("Approved", email=f"a{i}@x.com").gate_pass.pass_code for i in range(5)}
    assert len(codes) == 5


def test_cannot_approve_twice(app):
    visit = make_visit("Approved")
    with pytest.raises(ServiceError):
        services.approve_request(visit, admin())


@pytest.mark.parametrize("bad_host", ["999", "abc", None])
def test_approve_rejects_invalid_host(app, bad_host):
    visit = make_visit()
    if bad_host is None:
        services.approve_request(visit, admin(), None)  # None means "assign later"
        return
    with pytest.raises(ServiceError):
        services.approve_request(visit, admin(), bad_host)
    assert visit.status == "Pending"


def test_only_host_role_can_be_assigned(app):
    visit = make_visit()
    with pytest.raises(ServiceError):
        services.approve_request(visit, admin(), guard().id)


def test_inactive_host_cannot_be_assigned(app):
    inactive = make_user("host", email="old@campus.edu", active=False)
    with pytest.raises(ServiceError):
        services.approve_request(make_visit(), admin(), inactive.id)


def test_reject_needs_reason(app):
    visit = make_visit()
    with pytest.raises(ServiceError):
        services.reject_request(visit, admin(), "  ")
    with pytest.raises(ServiceError):
        services.reject_request(visit, admin(), "x" * 501)
    services.reject_request(visit, admin(), "Not on the guest list")
    assert visit.status == "Rejected" and visit.rejection_reason == "Not on the guest list"
    assert visit.gate_pass is None


def test_cannot_reject_approved(app):
    with pytest.raises(ServiceError):
        services.reject_request(make_visit("Approved"), admin(), "too late")


# ------------------------------------------------------------- cancel / host / complete

def test_cancel_deactivates_pass(app):
    visit = make_visit("Approved")
    services.cancel_request(visit, admin())
    assert visit.status == "Cancelled" and not visit.gate_pass.is_active


def test_cannot_cancel_checked_in(app):
    with pytest.raises(ServiceError):
        services.cancel_request(make_visit("Checked In"), admin())


def test_assign_host_replaces_previous_host(app):
    other = make_user("host", email="host2@campus.edu", name="Dr. Two")
    visit = make_visit("Approved", host=host())
    services.assign_host(visit, admin(), other.id)
    assert visit.host_assignment.host == other
    assert HostAssignment.query.count() == 1


def test_assign_host_needs_approval(app):
    with pytest.raises(ServiceError):
        services.assign_host(make_visit(), admin(), host().id)


def test_complete_only_after_checkout(app):
    with pytest.raises(ServiceError):
        services.complete_request(make_visit("Checked In"), admin())
    visit = make_visit("Checked Out", email="b@x.com")
    services.complete_request(visit, admin())
    assert visit.status == "Completed"


# ------------------------------------------------------------------------- gate rules

def test_unknown_or_empty_code(app):
    for code in ("nope", "", None, "   "):
        check = services.evaluate_pass(code)
        assert check.action is None and "not found" in check.message


def test_valid_pass_today_can_check_in(app):
    visit = make_visit("Approved")
    check = services.evaluate_pass(visit.gate_pass.pass_code)
    assert check.action == "check_in" and check.visit is visit


def test_pass_code_is_trimmed(app):
    visit = make_visit("Approved")
    assert services.evaluate_pass(f"  {visit.gate_pass.pass_code}\n").action == "check_in"


def test_too_early_and_expired(app):
    early = make_visit("Approved", days=2, email="e@x.com")
    check = services.evaluate_pass(early.gate_pass.pass_code)
    assert check.action is None and "Too early" in check.message

    late = make_visit("Approved", days=-1, email="l@x.com")
    check = services.evaluate_pass(late.gate_pass.pass_code)
    assert check.action is None and "expired" in check.message


def test_pass_expires_at_valid_until(app):
    visit = make_visit("Approved")
    visit.gate_pass.valid_until = utcnow().replace(microsecond=0) - timedelta(minutes=1)
    db.session.commit()
    assert "expired" in services.evaluate_pass(visit.gate_pass.pass_code).message


def test_cancelled_pass_is_blocked(app):
    visit = make_visit("Cancelled")
    check = services.evaluate_pass(visit.gate_pass.pass_code)
    assert check.action is None and "cancelled" in check.message


def test_full_gate_cycle(app):
    visit = make_visit("Approved")
    code = visit.gate_pass.pass_code

    services.check_in(code, guard())
    assert visit.status == "Checked In"
    record = CheckInOut.query.one()
    assert record.check_out_time is None and record.security == guard()

    with pytest.raises(ServiceError):  # second scan while inside is a check-out, not a check-in
        services.check_in(code, guard())

    services.check_out(code, guard())
    assert visit.status == "Checked Out"
    assert record.check_out_time is not None
    assert not visit.gate_pass.is_active

    with pytest.raises(ServiceError) as error:
        services.check_in(code, guard())
    assert "already used" in str(error.value)


def test_cannot_check_out_without_check_in(app):
    visit = make_visit("Approved")
    with pytest.raises(ServiceError):
        services.check_out(visit.gate_pass.pass_code, guard())


def test_checkout_allowed_after_pass_expiry(app):
    """A visitor who stays past midnight must still be able to leave."""
    visit = make_visit("Checked In")
    visit.gate_pass.valid_until = utcnow() - timedelta(hours=5)
    db.session.commit()
    services.check_out(visit.gate_pass.pass_code, guard())
    assert visit.status == "Checked Out"


# ---------------------------------------------------------------------------- utilities

def test_end_of_day_uses_campus_timezone(app):
    # Dhaka is UTC+6, so 23:59:59 local is 17:59:59 UTC.
    stamp = end_of_day_utc(date(2026, 9, 24))
    assert (stamp.hour, stamp.minute, stamp.second) == (17, 59, 59)
