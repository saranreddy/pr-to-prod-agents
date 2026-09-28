"""Tests for the Notes API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, notes_db, next_id

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the database before each test."""
    notes_db.clear()
    global next_id
    next_id = 1
    yield


def test_health():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_note():
    """Test creating a note."""
    response = client.post(
        "/api/notes",
        json={"title": "Test Note", "content": "This is a test note"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Test Note"
    assert data["content"] == "This is a test note"
    assert "created_at" in data
    assert "updated_at" in data


def test_list_notes():
    """Test listing notes."""
    client.post("/api/notes", json={"title": "Note 1", "content": "Content 1"})
    client.post("/api/notes", json={"title": "Note 2", "content": "Content 2"})

    response = client.get("/api/notes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Note 1"
    assert data[1]["title"] == "Note 2"


def test_get_note():
    """Test getting a note by ID."""
    create_response = client.post(
        "/api/notes",
        json={"title": "Test Note", "content": "Test Content"},
    )
    note_id = create_response.json()["id"]

    response = client.get(f"/api/notes/{note_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == note_id
    assert data["title"] == "Test Note"


def test_get_note_not_found():
    """Test getting a non-existent note."""
    response = client.get("/api/notes/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


def test_update_note():
    """Test updating a note."""
    create_response = client.post(
        "/api/notes",
        json={"title": "Original", "content": "Original content"},
    )
    note_id = create_response.json()["id"]

    response = client.put(
        f"/api/notes/{note_id}",
        json={"title": "Updated", "content": "Updated content"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["content"] == "Updated content"


def test_update_note_not_found():
    """Test updating a non-existent note."""
    response = client.put(
        "/api/notes/999",
        json={"title": "Test", "content": "Test"},
    )
    assert response.status_code == 404


def test_delete_note():
    """Test deleting a note."""
    create_response = client.post(
        "/api/notes",
        json={"title": "To Delete", "content": "Will be deleted"},
    )
    note_id = create_response.json()["id"]

    response = client.delete(f"/api/notes/{note_id}")
    assert response.status_code == 204

    get_response = client.get(f"/api/notes/{note_id}")
    assert get_response.status_code == 404


def test_delete_note_not_found():
    """Test deleting a non-existent note."""
    response = client.delete("/api/notes/999")
    assert response.status_code == 404
