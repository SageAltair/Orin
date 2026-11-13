import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from orin_api import admin_cli
from orin_api.database import Base
from orin_api.models import AdminAuditEvent, User


def test_admin_cli_role_change_records_operator(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with sessions.begin() as session:
            user = User(email="cli-member@example.test", password_hash="unused", display_name="CLI Member")
            session.add(user)
            session.flush()
            user_id = user.id

        monkeypatch.setattr(admin_cli, "SessionLocal", sessions)
        monkeypatch.setenv("ORIN_ADMIN_OPERATOR", "release-operator@example.test")
        monkeypatch.setattr(sys, "argv", ["orin-admin", "promote", "cli-member@example.test"])
        admin_cli.main()

        with sessions() as session:
            assert session.get(User, user_id).is_admin is True
            event = session.scalar(select(AdminAuditEvent))
            assert event is not None
            assert event.action == "admin.role.promoted"
            assert event.target_id == str(user_id)
            assert event.detail_json == {
                "operator": "release-operator@example.test",
                "previous_is_admin": False,
                "is_admin": True,
            }
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_admin_cli_role_change_can_use_explicit_operator_argument(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with sessions.begin() as session:
            user = User(email="cli-demote@example.test", password_hash="unused", display_name="CLI Admin", is_admin=True)
            session.add(user)
            session.flush()
            user_id = user.id

        monkeypatch.setattr(admin_cli, "SessionLocal", sessions)
        monkeypatch.delenv("ORIN_ADMIN_OPERATOR", raising=False)
        monkeypatch.setattr(sys, "argv", [
            "orin-admin", "demote", "cli-demote@example.test", "--operator", "release-engineer",
        ])
        admin_cli.main()

        with sessions() as session:
            assert session.get(User, user_id).is_admin is False
            event = session.scalar(select(AdminAuditEvent))
            assert event is not None
            assert event.action == "admin.role.demoted"
            assert event.detail_json["operator"] == "release-engineer"
            assert event.detail_json["previous_is_admin"] is True
            assert event.detail_json["is_admin"] is False
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
