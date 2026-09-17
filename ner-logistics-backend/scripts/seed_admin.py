"""
Seed an initial admin account for development and testing.

Usage:
    python scripts/seed_admin.py

Credentials are read from environment variables / .env file:
    SEED_ADMIN_USERNAME  (default: admin)
    SEED_ADMIN_PASSWORD  (default: admin_dev_password)
    SEED_ADMIN_EMAIL     (default: admin@ner-logistics.dev)

This script is IDEMPOTENT: running it multiple times will not create
duplicate accounts.

⚠️  The default credentials are for DEVELOPMENT/TESTING ONLY.
    Override them via environment variables in any real deployment.
"""
import os
import sys

# Add project root to path so we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.database import SessionLocal, Base, engine
from app.models import User
from app.services.auth_service import get_user_by_username, hash_password

# Ensure tables exist
Base.metadata.create_all(bind=engine)


def seed_admin():
    db = SessionLocal()
    try:
        existing = get_user_by_username(db, settings.seed_admin_username)
        if existing:
            print(
                f"Admin user '{settings.seed_admin_username}' already exists "
                f"(id={existing.id}, role={existing.role}). Skipping."
            )
            return

        admin = User(
            username=settings.seed_admin_username,
            email=settings.seed_admin_email,
            hashed_password=hash_password(settings.seed_admin_password),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(
            f"[OK] Admin user created:\n"
            f"  username: {admin.username}\n"
            f"  email:    {admin.email}\n"
            f"  role:     {admin.role}\n"
            f"  id:       {admin.id}\n"
            f"\n"
            f"WARNING: These are DEVELOPMENT credentials.\n"
            f"   Override via SEED_ADMIN_USERNAME, SEED_ADMIN_PASSWORD, "
            f"SEED_ADMIN_EMAIL env vars for real deployments."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
