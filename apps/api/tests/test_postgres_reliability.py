"""Concurrency regression on an explicitly isolated PostgreSQL database."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from orin_api.database import Base
from orin_api.models import User, KnowledgeDocument
from orin_api.workspace_router import DocumentUpdate, update_knowledge_document
from fastapi import HTTPException


@pytest.mark.skipif(not os.getenv("ORIN_FOCUS_TEST_DATABASE_URL"), reason="requires an isolated PostgreSQL database")
def test_simultaneous_writing_updates_cannot_both_win():
    engine = create_engine(os.environ["ORIN_FOCUS_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email=f"concurrent-{uuid.uuid4()}@example.test", display_name="Writer", password_hash="fake")
        session.add(user); session.flush()
        note = KnowledgeDocument(user_id=user.id, title="Concurrent note", content="original")
        session.add(note); session.flush()
        note_id, version = note.id, note.version
    barrier = Barrier(2)
    def edit(content):
        with sessions() as session:
            barrier.wait(timeout=5)
            try:
                return update_knowledge_document(note_id, DocumentUpdate(content=content, expected_version=version), user, session)["content"]
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(edit, ["one", "two"]))
        assert outcomes.count(409) == 1
        assert sum(value in {"one", "two"} for value in outcomes) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
