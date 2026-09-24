import re
import secrets
from datetime import datetime, time, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import abort, current_app
from flask_login import current_user

from app import login_manager
from app.constants import STAFF_ROLES

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ time helpers
# Times are stored as naive UTC. "Today" and display times use APP_TIMEZONE.

def utcnow():
    """Current UTC time as a naive datetime (what the DateTime columns store)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tz():
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def today_local():
    """Today's date in the campus timezone."""
    return datetime.now(_tz()).date()


def to_local(value):
    """Convert a stored (naive UTC) datetime to the campus timezone."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(_tz())


def end_of_day_utc(day):
    """23:59:59 of a local date, as naive UTC. Used as a gate pass expiry."""
    local_end = datetime.combine(day, time(23, 59, 59), tzinfo=_tz())
    return local_end.astimezone(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------- id helpers

def generate_request_id(day=None):
    """Return the next visit request ID for a day: VR-YYYYMMDD-XXXX."""
    from app.models import VisitRequest

    day = day or today_local()
    prefix = f"VR-{day:%Y%m%d}-"
    last = (
        VisitRequest.query.filter(VisitRequest.request_id.like(prefix + "%"))
        .order_by(VisitRequest.request_id.desc())
        .first()
    )
    sequence = int(last.request_id.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{sequence:04d}"


def generate_pass_code():
    """Secure random token. This is the value the QR code contains."""
    return secrets.token_urlsafe(24)


# ------------------------------------------------------------------ access control

def roles_required(*roles):
    """Allow only logged-in users whose role is in `roles`. Others get login page / 403."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


staff_required = roles_required(*STAFF_ROLES)
