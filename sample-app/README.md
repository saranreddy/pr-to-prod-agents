# Sample Notes API

A simple FastAPI application for managing notes. This is the target application used in PR-to-Production agent demonstrations.

## Features

- Create, read, update, and delete notes
- Health check endpoint
- Full test coverage

## Running Locally

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Running Tests

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `GET /api/notes` - List all notes
- `POST /api/notes` - Create a note
- `GET /api/notes/{id}` - Get a note
- `PUT /api/notes/{id}` - Update a note
- `DELETE /api/notes/{id}` - Delete a note
