"""Seed the database with the initial admin and salesperson accounts.

Run with: poetry run python -m app.seed
"""

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.settings import OrgSettings
from app.models.user import User, UserRole


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                name="Admin User",
                email="admin@samitsolutions.com",
                password_hash=hash_password("ChangeMe123!"),
                role=UserRole.ADMIN,
            )
            salesperson = User(
                name="Sales Rep",
                email="sales@samitsolutions.com",
                password_hash=hash_password("ChangeMe123!"),
                role=UserRole.SALESPERSON,
            )
            db.add_all([admin, salesperson])
            print("Created admin@samitsolutions.com and sales@samitsolutions.com (password: ChangeMe123!)")
        else:
            print("Users already exist, skipping user seed.")

        if db.query(OrgSettings).count() == 0:
            db.add(OrgSettings(org_name="Sam IT Solutions"))
            print("Created default org settings.")
        else:
            print("Org settings already exist, skipping.")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
