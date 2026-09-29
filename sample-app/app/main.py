"""Sample Notes API - Target application for agent demonstrations."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Notes API", version="1.0.0")


class Note(BaseModel):
    """Note model."""

    id: Optional[int] = None
    title: str
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


notes_db: dict[int, Note] = {}
next_id = 1


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/notes", response_model=List[Note])
async def list_notes() -> List[Note]:
    """List all notes."""
    return list(notes_db.values())


@app.post("/api/notes", response_model=Note, status_code=201)
async def create_note(note: Note) -> Note:
    """Create a new note."""
    global next_id
    
    note.id = next_id
    note.created_at = datetime.now(timezone.utc)
    note.updated_at = datetime.now(timezone.utc)
    
    notes_db[next_id] = note
    next_id += 1
    
    return note


@app.get("/api/notes/{note_id}", response_model=Note)
async def get_note(note_id: int) -> Note:
    """Get a note by ID."""
    if note_id not in notes_db:
        raise HTTPException(status_code=404, detail="Note not found")
    return notes_db[note_id]


@app.put("/api/notes/{note_id}", response_model=Note)
async def update_note(note_id: int, note: Note) -> Note:
    """Update a note."""
    if note_id not in notes_db:
        raise HTTPException(status_code=404, detail="Note not found")
    
    existing_note = notes_db[note_id]
    existing_note.title = note.title
    existing_note.content = note.content
    existing_note.updated_at = datetime.now(timezone.utc)
    
    return existing_note


@app.delete("/api/notes/{note_id}", status_code=204)
async def delete_note(note_id: int) -> None:
    """Delete a note."""
    if note_id not in notes_db:
        raise HTTPException(status_code=404, detail="Note not found")
    del notes_db[note_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
