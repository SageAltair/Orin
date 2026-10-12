import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.main import app
from orin_api.models import (
    Activity,
    ActivityType,
    CreativeDocumentCard,
    CreativeOutlineItem,
    IdeaDocumentLink,
    IdeaInbox,
    User,
)


@pytest.fixture
def sessions() -> Generator[tuple[sessionmaker, uuid.UUID], None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        user = User(email="studio@example.test", password_hash="test-hash", display_name="Studio")
        session.add(user)
        session.flush()
        owner_id = user.id
    try:
        yield factory, owner_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(sessions: tuple[sessionmaker, uuid.UUID]) -> Generator[TestClient, None, None]:
    factory, owner_id = sessions

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    def current_user() -> User:
        with factory() as session:
            user = session.get(User, owner_id)
            assert user is not None
            return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _project(client: TestClient, name: str = "The Small Voice") -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"name": name, "objective": "Help people grow"})
    assert response.status_code == 201, response.text
    return response.json()


def _note(client: TestClient, title: str = "Opening scene") -> dict[str, object]:
    response = client.post(
        "/api/v1/knowledge/documents",
        json={"title": title, "content": "A first line.", "document_type": "draft"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Ideas ---


def test_idea_capture_uses_first_line_as_title(client: TestClient) -> None:
    response = client.post("/api/v1/creative/ideas", json={"text": "A lighthouse keeper\nwho only speaks in questions."})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "A lighthouse keeper"
    assert body["content"] == "A lighthouse keeper\nwho only speaks in questions."
    assert body["status"] == "active"
    assert body["linked_document_ids"] == []


def test_idea_capture_rejects_empty_text(client: TestClient) -> None:
    assert client.post("/api/v1/creative/ideas", json={"text": ""}).status_code == 422


def test_idea_capture_rejects_unknown_fields(client: TestClient) -> None:
    assert client.post("/api/v1/creative/ideas", json={"text": "Fine", "status": "archived"}).status_code == 422


def test_ideas_can_be_filtered_by_status(client: TestClient) -> None:
    client.post("/api/v1/creative/ideas", json={"text": "First idea"})
    second = client.post("/api/v1/creative/ideas", json={"text": "Second idea"})

    assert len(client.get("/api/v1/creative/ideas?status=active").json()) == 2
    assert client.get("/api/v1/creative/ideas?status=archived").json() == []
    assert len(client.get("/api/v1/creative/ideas?status=all").json()) == 2

    patched = client.patch(f"/api/v1/creative/ideas/{second.json()['id']}", json={"text": "Second idea, rewritten"})
    assert patched.status_code == 200
    assert patched.json()["title"] == "Second idea, rewritten"
    assert patched.json()["content"] == "Second idea, rewritten"


def test_idea_update_keeps_previous_title_when_new_text_is_blank(client: TestClient) -> None:
    created = client.post("/api/v1/creative/ideas", json={"text": "Keep this title"})

    patched = client.patch(f"/api/v1/creative/ideas/{created.json()['id']}", json={"text": "   "})

    assert patched.status_code == 200
    assert patched.json()["title"] == "Keep this title"


def test_idea_update_rejects_unknown_idea(client: TestClient) -> None:
    assert client.patch(f"/api/v1/creative/ideas/{uuid.uuid4()}", json={"text": "Nope"}).status_code == 404


def test_idea_status_filter_rejects_unknown_value(client: TestClient) -> None:
    assert client.get("/api/v1/creative/ideas?status=published").status_code == 422


# --- Idea links ---


def test_idea_links_sync_linked_document_ids_and_can_be_removed(client: TestClient) -> None:
    idea = client.post("/api/v1/creative/ideas", json={"text": "An idea worth linking"})
    note = _note(client)
    idea_id = idea.json()["id"]

    linked = client.post(
        f"/api/v1/creative/ideas/{idea_id}/links",
        json={"document_id": note["id"], "link_type": "extends", "note": "The ending fits here."},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["link_type"] == "extends"
    assert linked.json()["note"] == "The ending fits here."

    idea_after_link = client.get("/api/v1/creative/ideas?status=active").json()[0]
    assert idea_after_link["linked_document_ids"] == [note["id"]]

    links = client.get(f"/api/v1/creative/ideas/{idea_id}/links").json()
    assert [row["document_id"] for row in links] == [note["id"]]

    assert client.delete(f"/api/v1/creative/ideas/{idea_id}/links/{note['id']}").status_code == 204
    assert client.get("/api/v1/creative/ideas?status=active").json()[0]["linked_document_ids"] == []


def test_repeating_an_identical_link_does_not_duplicate_it(client: TestClient) -> None:
    idea = client.post("/api/v1/creative/ideas", json={"text": "One idea, one note"})
    note = _note(client)
    idea_id = idea.json()["id"]
    payload = {"document_id": note["id"], "link_type": "supports"}

    client.post(f"/api/v1/creative/ideas/{idea_id}/links", json=payload)
    again = client.post(f"/api/v1/creative/ideas/{idea_id}/links", json=payload)

    assert again.status_code == 200
    assert len(client.get(f"/api/v1/creative/ideas/{idea_id}/links").json()) == 1




# --- Outline items ---


def test_outline_items_require_at_most_one_target(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/outline"

    note = _note(client)
    both = client.post(
        base, json={"title": "Both", "parent_id": str(uuid.uuid4()), "document_id": note["id"]}
    )
    assert both.status_code == 422
    assert both.json()["detail"] == "Provide only one of parent_id or document_id"


def test_outline_items_nest_by_parent_and_order_by_position(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/outline"

    chapter = client.post(base, json={"title": "Chapter one", "kind": "chapter", "position": 1})
    assert chapter.status_code == 201, chapter.text
    parent_id = chapter.json()["id"]

    client.post(base, json={"title": "The keeper waits", "kind": "scene", "parent_id": parent_id, "position": 2})
    client.post(base, json={"title": "A question arrives", "kind": "scene", "parent_id": parent_id, "position": 1})

    everything = client.get(base).json()
    assert {row["title"] for row in everything} == {"Chapter one", "The keeper waits", "A question arrives"}

    children = client.get(base, params={"parent_id": parent_id}).json()
    assert [row["title"] for row in children] == ["A question arrives", "The keeper waits"]
    assert children[0]["status"] == "planned"
    assert children[0]["parent_id"] == parent_id


def test_outline_item_can_be_moved_and_marked_done(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/outline"
    created = client.post(base, json={"title": "A loose beat", "kind": "beat"})

    patched = client.patch(f"{base}/{created.json()['id']}", json={"title": "A tightened beat", "status": "done", "position": 3})

    assert patched.status_code == 200
    assert patched.json()["title"] == "A tightened beat"
    assert patched.json()["status"] == "done"
    assert patched.json()["position"] == 3


def test_outline_item_patch_rejects_unknown_status(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/outline"
    created = client.post(base, json={"title": "Beat", "kind": "beat"})

    assert client.patch(f"{base}/{created.json()['id']}", json={"status": "shipped"}).status_code == 422


def test_outline_routes_reject_unknown_project(client: TestClient) -> None:
    missing = str(uuid.uuid4())

    assert client.get(f"/api/v1/creative/projects/{missing}/outline").status_code == 404
    assert client.post(
        f"/api/v1/creative/projects/{missing}/outline",
        json={"title": "X", "parent_id": str(uuid.uuid4())},
    ).status_code == 404
    assert client.patch(f"/api/v1/creative/projects/{missing}/outline/{uuid.uuid4()}", json={"title": "X"}).status_code == 404


def test_outline_update_rejects_unknown_item(client: TestClient) -> None:
    project = _project(client)

    assert client.patch(
        f"/api/v1/creative/projects/{project['id']}/outline/{uuid.uuid4()}", json={"title": "Ghost"}
    ).status_code == 404


# --- Document cards ---


def test_document_card_round_trip_carries_editorial_intent(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/cards"

    created = client.post(base, json={
        "title": "Chapter one",
        "summary": "The keeper asks his first question.",
        "purpose": "Introduce the rule of the world.",
        "central_question": "Can silence be a gift?",
        "point_of_view": "Close third",
        "status": "drafting",
        "position": 2,
    })

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["central_question"] == "Can silence be a gift?"
    assert body["point_of_view"] == "Close third"
    assert body["status"] == "drafting"

    assert len(client.get(base).json()) == 1
    assert client.get(base, params={"status": "ready"}).json() == []
    assert len(client.get(base, params={"status": "drafting"}).json()) == 1


def test_document_card_can_be_advanced_to_published(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/cards"
    created = client.post(base, json={"title": "Letter to the reader"})

    patched = client.patch(f"{base}/{created.json()['id']}", json={"title": "Letter to the reader", "status": "published"})

    assert patched.status_code == 200
    assert patched.json()["status"] == "published"


def test_document_card_rejects_unknown_status_and_unknown_card(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/cards"
    created = client.post(base, json={"title": "Draft card"})

    assert client.patch(f"{base}/{created.json()['id']}", json={"title": "Draft card", "status": "shipped"}).status_code == 422
    assert client.patch(f"{base}/{uuid.uuid4()}", json={"title": "Ghost"}).status_code == 404


def test_card_status_filter_rejects_unknown_value(client: TestClient) -> None:
    project = _project(client)

    assert client.get(f"/api/v1/creative/projects/{project['id']}/cards?status=shipped").status_code == 422


def test_card_routes_reject_unknown_project(client: TestClient) -> None:
    missing = str(uuid.uuid4())

    assert client.get(f"/api/v1/creative/projects/{missing}/cards").status_code == 404
    assert client.post(f"/api/v1/creative/projects/{missing}/cards", json={"title": "X"}).status_code == 404
    assert client.patch(f"/api/v1/creative/projects/{missing}/cards/{uuid.uuid4()}", json={"title": "X"}).status_code == 404

def test_link_rejects_unknown_document_and_unknown_idea(client: TestClient) -> None:
    idea = client.post("/api/v1/creative/ideas", json={"text": "Orphan idea"})

    missing_document = client.post(
        f"/api/v1/creative/ideas/{idea.json()['id']}/links", json={"document_id": str(uuid.uuid4())}
    )
    assert missing_document.status_code == 404
    assert missing_document.json()["detail"] == "Document not found"

    note = _note(client)
    missing_idea = client.post(f"/api/v1/creative/ideas/{uuid.uuid4()}/links", json={"document_id": note["id"]})
    assert missing_idea.status_code == 404
    assert missing_idea.json()["detail"] == "Idea not found"


def test_link_rejects_unknown_link_type(client: TestClient) -> None:
    idea = client.post("/api/v1/creative/ideas", json={"text": "Typed idea"})
    note = _note(client)

    response = client.post(
        f"/api/v1/creative/ideas/{idea.json()['id']}/links",
        json={"document_id": note["id"], "link_type": "somehow"},
    )

    assert response.status_code == 422


def test_removing_an_unknown_link_is_a_404(client: TestClient) -> None:
    idea = client.post("/api/v1/creative/ideas", json={"text": "Lonely idea"})
    note = _note(client)

    response = client.delete(f"/api/v1/creative/ideas/{idea.json()['id']}/links/{note['id']}")

    assert response.status_code == 404


# --- Ownership ---


def test_creative_routes_do_not_leak_another_users_records(
    client: TestClient, sessions: tuple[sessionmaker, uuid.UUID]
) -> None:
    factory, owner_id = sessions
    idea_id = client.post("/api/v1/creative/ideas", json={"text": "Private idea"}).json()["id"]
    note_id = _note(client)["id"]
    project_id = _project(client)["id"]

    with factory.begin() as session:
        intruder = User(email="intruder@example.test", password_hash="test-hash", display_name="Intruder")
        session.add(intruder)
        session.flush()
        intruder_id = intruder.id

    def intruder_user() -> User:
        with factory() as session:
            user = session.get(User, intruder_id)
            assert user is not None
            return user

    app.dependency_overrides[get_current_user] = intruder_user
    try:
        assert client.patch(f"/api/v1/creative/ideas/{idea_id}", json={"text": "Taken over"}).status_code == 404
        assert client.post(f"/api/v1/creative/ideas/{idea_id}/links", json={"document_id": note_id}).status_code == 404
        assert client.get(f"/api/v1/creative/ideas/{idea_id}/links").status_code == 404
        assert client.delete(f"/api/v1/creative/ideas/{idea_id}/links/{note_id}").status_code == 404
        assert client.get(f"/api/v1/creative/projects/{project_id}/outline").status_code == 404
        assert client.get(f"/api/v1/creative/projects/{project_id}/cards").status_code == 404
    finally:
        def owner_user() -> User:
            with factory() as session:
                user = session.get(User, owner_id)
                assert user is not None
                return user

        app.dependency_overrides[get_current_user] = owner_user

    # The owner still sees the untouched record after the intruder's attempts.
    assert client.get("/api/v1/creative/ideas?status=active").json()[0]["content"] == "Private idea"


# --- Domain rules ---


def test_linked_document_ids_are_stored_as_a_deduplicated_csv(
    client: TestClient, sessions: tuple[sessionmaker, uuid.UUID]
) -> None:
    factory, _ = sessions
    idea_id = client.post("/api/v1/creative/ideas", json={"text": "Many links"}).json()["id"]
    first_id = _note(client, "One")["id"]
    second_id = _note(client, "Two")["id"]
    expected = sorted([str(first_id), str(second_id)])

    client.post(f"/api/v1/creative/ideas/{idea_id}/links", json={"document_id": first_id, "link_type": "extends"})
    client.post(f"/api/v1/creative/ideas/{idea_id}/links", json={"document_id": second_id, "link_type": "supports"})

    with factory() as session:
        idea = session.get(IdeaInbox, uuid.UUID(idea_id))
        assert idea is not None
        stored = [item for item in idea.linked_document_ids.split(",") if item]
        assert stored == sorted(stored)
        assert len(stored) == len(set(stored))
        assert stored == expected


def test_outline_target_check_constraint_is_declared() -> None:
    constraints = CreativeOutlineItem.__table_args__
    assert any(getattr(item, "name", None) == "ck_outline_item_at_most_one_target" for item in constraints)


def test_root_outline_items_are_allowed_but_both_targets_are_rejected(client: TestClient) -> None:
    project = _project(client)
    base = f"/api/v1/creative/projects/{project['id']}/outline"

    root = client.post(base, json={"title": "Act one", "kind": "act"})
    assert root.status_code == 201, root.text
    assert root.json()["parent_id"] is None
    assert root.json()["document_id"] is None

    note = _note(client)
    rejected = client.post(
        base, json={"title": "Both", "parent_id": root.json()["id"], "document_id": note["id"]}
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Provide only one of parent_id or document_id"


def test_idea_link_uniqueness_is_declared() -> None:
    assert IdeaDocumentLink.__table_args__[0].name == "uq_idea_document_link"


def test_creative_activity_types_are_registered() -> None:
    expected = {
        "idea_created",
        "idea_linked",
        "idea_unlinked",
        "outline_item_created",
        "outline_item_updated",
        "document_card_created",
        "document_card_updated",
    }
    assert expected <= {member.value for member in ActivityType}


def test_creative_tables_use_the_expected_names() -> None:
    assert {IdeaInbox.__tablename__, CreativeOutlineItem.__tablename__,
            CreativeDocumentCard.__tablename__, IdeaDocumentLink.__tablename__} == {
        "idea_inbox", "creative_outline_items", "creative_document_cards", "idea_document_links"}


def test_row_defaults_match_the_api_contract(sessions: tuple[sessionmaker, uuid.UUID]) -> None:
    factory, owner_id = sessions
    with factory.begin() as session:
        idea = IdeaInbox(user_id=owner_id, title="Defaults", content=None)
        card = CreativeDocumentCard(user_id=owner_id, title="Card defaults")
        session.add_all([idea, card])
        session.flush()
        idea_id, card_id = idea.id, card.id

    with factory() as session:
        assert session.get(IdeaInbox, idea_id).status == "active"
        assert session.get(CreativeDocumentCard, card_id).status == "todo"
        assert session.get(CreativeOutlineItem, uuid.uuid4()) is None


def test_capturing_an_idea_emits_activity(
    client: TestClient, sessions: tuple[sessionmaker, uuid.UUID]
) -> None:
    factory, _ = sessions
    created = client.post("/api/v1/creative/ideas", json={"text": "A traceable idea"})
    idea_id = created.json()["id"]

    with factory() as session:
        activity = session.scalar(
            select(Activity)
            .where(Activity.activity_type == ActivityType.IDEA_CREATED)
            .order_by(Activity.created_at.desc())
        )
        assert activity is not None
        assert activity.summary == "Captured idea: A traceable idea"
        assert activity.metadata_json["entity_id"] == idea_id
        assert activity.project_id is None


def test_creative_tables_exist_in_the_schema(sessions: tuple[sessionmaker, uuid.UUID]) -> None:
    factory, _ = sessions
    with factory() as session:
        tables = set(session.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars())
    assert {"idea_inbox", "creative_outline_items", "creative_document_cards", "idea_document_links"} <= tables

