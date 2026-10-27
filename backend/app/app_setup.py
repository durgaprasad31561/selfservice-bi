"""Create the app-schema tables and seed one demo user per role (idempotent)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import get_settings
from app.db import get_admin_engine
from app.models import Base, Role, User

log = logging.getLogger(__name__)


def create_app_tables() -> None:
    Base.metadata.create_all(get_admin_engine())


def seed_demo_users() -> list[str]:
    """Create missing demo users from .env; existing users are left unchanged."""
    s = get_settings()
    demo = [
        (s.demo_admin_email, s.demo_admin_password, Role.admin, "Demo Admin"),
        (s.demo_analyst_email, s.demo_analyst_password, Role.analyst, "Demo Analyst"),
        (s.demo_viewer_email, s.demo_viewer_password, Role.viewer, "Demo Viewer"),
    ]
    created = []
    with Session(get_admin_engine()) as db:
        for email, password, role, name in demo:
            if not email or not password:
                continue
            email = email.strip().lower()
            if db.scalar(select(User).where(User.email == email)):
                continue
            db.add(
                User(email=email, full_name=name, password_hash=hash_password(password), role=role)
            )
            created.append(email)
        db.commit()
    if created:
        log.info("seeded demo users: %s", ", ".join(created))
    return created


def init_app_database() -> None:
    create_app_tables()
    seed_demo_users()
