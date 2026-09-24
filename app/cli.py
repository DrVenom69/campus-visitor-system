"""Command line helpers. Run with:  flask --app run <command>"""
import secrets
from datetime import timedelta

import click

from app import db
from app.constants import CREATABLE_ROLES
from app.models import CheckInOut, GatePass, HostAssignment, User, Visitor, VisitRequest
from app.utils import end_of_day_utc, generate_request_id, today_local, utcnow


def _create_user(name, email, password, role):
    email = email.strip().lower()
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException(f"A user with {email} already exists.")
    user = User(name=name.strip(), email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f"{role.title()} account {email} created.")


def register_cli(app):
    @app.cli.command("init-db")
    @click.option("--reset", is_flag=True, help="Drop all tables first. Deletes all data.")
    def init_db(reset):
        """Create the database tables."""
        if reset:
            db.drop_all()
            click.echo("Dropped all tables.")
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(name, email, password):
        """Create an admin account."""
        _create_user(name, email, password, "admin")

    @app.cli.command("create-user")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--role", type=click.Choice(CREATABLE_ROLES), prompt=True)
    @click.password_option()
    def create_user(name, email, role, password):
        """Create an admin, host or security account."""
        _create_user(name, email, password, role)

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add sample visitors and requests so every page has something to show."""
        if VisitRequest.query.count():
            raise click.ClickException("Visit requests already exist. Demo data not added.")

        host = User.query.filter_by(email="demo.host@campus.edu").first()
        if host is None:
            host = User(name="Dr. Demo Host", email="demo.host@campus.edu", role="host")
            host.set_password(secrets.token_urlsafe(16))  # random: nobody can log in as this account
            db.session.add(host)

        today = today_local()
        samples = [
            ("John Doe", "john@example.com", "Meeting", "Checked In", 0),
            ("Sarah Wilson", "sarah@example.com", "Interview", "Pending", 0),
            ("Robert Brown", "robert@example.com", "Delivery", "Checked Out", 0),
            ("Amina Rahman", "amina@example.com", "Event", "Approved", 0),
            ("Nadia Islam", "nadia@example.com", "Meeting", "Pending", 1),
            ("Karim Hossain", "karim@example.com", "Official work", "Rejected", 1),
            ("Tanvir Ahmed", "tanvir@example.com", "Interview", "Cancelled", 2),
        ]
        for name, email, purpose, status, offset in samples:
            visit_day = today + timedelta(days=offset)
            visit = VisitRequest(
                request_id=generate_request_id(today),
                visitor=Visitor(full_name=name, email=email, phone="01700000000"),
                purpose=purpose,
                visit_date=visit_day,
                status=status,
                rejection_reason="Demo rejection" if status == "Rejected" else None,
            )
            db.session.add(visit)
            db.session.flush()  # so the next generate_request_id sees this row

            if status in ("Approved", "Checked In", "Checked Out"):
                db.session.add(HostAssignment(visit_request=visit, host=host))
                gate_pass = GatePass(
                    visit_request=visit,
                    valid_until=end_of_day_utc(visit_day),
                    is_active=status != "Checked Out",
                )
                db.session.add(gate_pass)
                if status in ("Checked In", "Checked Out"):
                    db.session.add(CheckInOut(
                        gate_pass=gate_pass,
                        check_out_time=utcnow() if status == "Checked Out" else None,
                    ))

        db.session.commit()
        click.echo("Demo data added.")
