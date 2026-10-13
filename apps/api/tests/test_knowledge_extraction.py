import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api import knowledge_extraction
from orin_api.config import Settings
from orin_api.database import Base
from orin_api.models import KnowledgeDocument, KnowledgeExtractionJob, User


def test_extraction_job_saves_validated_result_and_source_version(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="extract@example.test", password_hash="test-hash", display_name="Extract")
        session.add(user)
        session.flush()
        document = KnowledgeDocument(user_id=user.id, title="Story idea", content="Create an outline.", document_type="idea", status="inbox")
        session.add(document)
        session.flush()
        job = KnowledgeExtractionJob(user_id=user.id, document_id=document.id, document_version=document.version)
        session.add(job)
        session.flush()
        job_id, document_id = job.id, document.id

    class Provider:
        def structured_output(self, **kwargs: object) -> str:
            assert "untrusted data" in str(kwargs["system"])
            return json.dumps({"summary": "An outline idea.", "topics": ["story"], "entities": [], "decisions": [],
                "open_questions": [], "candidate_actions": ["Draft an outline"], "date_mentions": []})

    monkeypatch.setattr(knowledge_extraction, "SessionLocal", sessions)
    monkeypatch.setattr(knowledge_extraction, "create_provider", lambda _: Provider())
    knowledge_extraction.process_extraction_job(job_id, Settings(ai_provider="openai", ai_model="gpt-4o-mini"))

    with sessions() as session:
        job = session.get(KnowledgeExtractionJob, job_id)
        document = session.get(KnowledgeDocument, document_id)
        assert job.status == "succeeded" and job.attempts == 1
        assert job.prompt_version == "knowledge-extraction-v1"
        assert document.extraction_status == "succeeded"
        assert document.extraction_version == document.version
        assert document.extracted_data["candidate_actions"] == ["Draft an outline"]
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_extraction_job_discards_stale_source_without_calling_provider(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        user = User(email="stale@example.test", password_hash="test-hash", display_name="Stale")
        session.add(user)
        session.flush()
        document = KnowledgeDocument(user_id=user.id, title="Changed", content="New version", document_type="idea", status="inbox", version=2)
        session.add(document)
        session.flush()
        job = KnowledgeExtractionJob(user_id=user.id, document_id=document.id, document_version=1)
        session.add(job)
        session.flush()
        job_id = job.id

    def unexpected_provider(_: object) -> object:
        raise AssertionError("A stale source must not be sent to an AI provider")

    monkeypatch.setattr(knowledge_extraction, "SessionLocal", sessions)
    monkeypatch.setattr(knowledge_extraction, "create_provider", unexpected_provider)
    knowledge_extraction.process_extraction_job(job_id, Settings(ai_provider="openai", ai_model="gpt-4o-mini"))
    with sessions() as session:
        job = session.scalar(select(KnowledgeExtractionJob).where(KnowledgeExtractionJob.id == job_id))
        assert job.status == "superseded"
    Base.metadata.drop_all(engine)
    engine.dispose()
