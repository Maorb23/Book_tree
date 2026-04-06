# Book Tree

Interactive Django app for organizing books as a visual reading tree.

## What this project includes

- Django backend with REST endpoints
- D3.js interactive tree visualization (zoom, pan, minimap)
- Add/edit/delete nodes from the UI
- Automatic cover lookup (ISBN/title)
- SQLite database for local development

## Tech stack

- Python 3.10+
- Django 4.2
- Django REST Framework
- D3.js (frontend)
- SQLite (default)

## Quick start

### 1. Go to the project folder

```bash
cd c:\Users\maorb\work\Book_tree
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. (Optional) Load sample data

```bash
python manage.py seed_data
```

### 6. Start the server

```bash
python manage.py runserver
```

Open:

- Landing page: http://127.0.0.1:8000/
- Tree view: http://127.0.0.1:8000/tree/
- Admin: http://127.0.0.1:8000/admin/

## API endpoints

- GET http://127.0.0.1:8000/api/tree/
- GET, POST http://127.0.0.1:8000/api/nodes/
- GET, PUT, PATCH, DELETE http://127.0.0.1:8000/api/nodes/<id>/
- GET http://127.0.0.1:8000/api/cover/?title=<title>&author=<author>&isbn=<isbn>

## Development notes

- DB file: db.sqlite3
- Static source files: static/
- Templates: templates/
- App code: tree/

## Troubleshooting

- If `python` is not recognized on Windows, use `py` instead:

```powershell
py -m venv .venv
py -m pip install -r requirements.txt
py manage.py migrate
py manage.py runserver
```

- If port 8000 is busy:

```bash
python manage.py runserver 8001
```

- If seed command fails, ensure migrations were applied first.

## Existing local environment in this repo

This repository contains a folder named `venvb/`. It appears to be an existing virtual environment. For reproducible setup, prefer creating a fresh `.venv` using the steps above.
