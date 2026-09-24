from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager
from app.utils import generate_pass_code, utcnow


class User(UserMixin, db.Model):
    """Staff and visitor accounts. `role` is one of app.constants.ROLES."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="visitor")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False)
    organization = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    visit_requests = db.relationship("VisitRequest", back_populates="visitor")


class VisitRequest(db.Model):
    __tablename__ = "visit_requests"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(20), unique=True, nullable=False, index=True)  # VR-YYYYMMDD-XXXX
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id"), nullable=False)
    purpose = db.Column(db.String(50), nullable=False)
    host_requested = db.Column(db.String(120))  # who the visitor says they are meeting
    visit_date = db.Column(db.Date, nullable=False, index=True)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    rejection_reason = db.Column(db.Text)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    visitor = db.relationship("Visitor", back_populates="visit_requests")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    host_assignment = db.relationship(
        "HostAssignment", back_populates="visit_request", uselist=False
    )
    gate_pass = db.relationship("GatePass", back_populates="visit_request", uselist=False)


class HostAssignment(db.Model):
    __tablename__ = "host_assignments"

    id = db.Column(db.Integer, primary_key=True)
    visit_request_id = db.Column(
        db.Integer, db.ForeignKey("visit_requests.id"), unique=True, nullable=False
    )
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    visit_request = db.relationship("VisitRequest", back_populates="host_assignment")
    host = db.relationship("User", foreign_keys=[host_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])


class GatePass(db.Model):
    __tablename__ = "gate_passes"

    id = db.Column(db.Integer, primary_key=True)
    visit_request_id = db.Column(
        db.Integer, db.ForeignKey("visit_requests.id"), unique=True, nullable=False
    )
    pass_code = db.Column(
        db.String(64), unique=True, nullable=False, index=True, default=generate_pass_code
    )  # the value encoded in the QR code
    issued_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    valid_until = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    visit_request = db.relationship("VisitRequest", back_populates="gate_pass")
    check_ins = db.relationship("CheckInOut", back_populates="gate_pass")


class CheckInOut(db.Model):
    __tablename__ = "check_in_out"

    id = db.Column(db.Integer, primary_key=True)
    gate_pass_id = db.Column(db.Integer, db.ForeignKey("gate_passes.id"), nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=False, default=utcnow)
    check_out_time = db.Column(db.DateTime)
    security_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # guard who scanned

    gate_pass = db.relationship("GatePass", back_populates="check_ins")
    security = db.relationship("User", foreign_keys=[security_id])
