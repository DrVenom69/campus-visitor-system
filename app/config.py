import os

from dotenv import load_dotenv

load_dotenv()  # reads .env from the project root, if present


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # Set DATABASE_URL in .env to use PostgreSQL. Without it the app falls back
    # to a local SQLite file so a teammate can still run it on day one.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///campus_visitor_dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Visit dates and "today" are calculated in this timezone (times are stored in UTC).
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Dhaka")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
