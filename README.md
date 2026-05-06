# Readwoods

Interactive Django app for organizing books as a visual reading tree.

## What this project includes

- Django backend with REST endpoints
- D3.js interactive tree visualization (zoom, pan, minimap)
- Add/edit/delete nodes from the UI
- Automatic cover lookup (ISBN/title)
- SQLite database for local development
- Community feature: posts + friend requests

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

If you are adding the community feature for the first time, run:

```bash
python manage.py makemigrations
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
- Register: http://127.0.0.1:8000/register/
- Login: http://127.0.0.1:8000/login/
- Tree view (requires login): http://127.0.0.1:8000/tree/
- Admin: http://127.0.0.1:8000/admin/

## API endpoints

- GET http://127.0.0.1:8000/api/tree/
- GET, POST (POST requires login) http://127.0.0.1:8000/api/nodes/
- GET, PUT, PATCH, DELETE (write requires login) http://127.0.0.1:8000/api/nodes/<id>/
- GET http://127.0.0.1:8000/api/cover/?title=<title>&author=<author>&isbn=<isbn>

## Development notes

- DB file: db.sqlite3
- Static source files: static/
- Templates: templates/
- App code: tree/

## Community pages

- Community feed: http://127.0.0.1:8000/community/
- Create post: http://127.0.0.1:8000/community/new/
- Find people: http://127.0.0.1:8000/community/people/
- Requests: http://127.0.0.1:8000/community/requests/
- Friends: http://127.0.0.1:8000/community/friends/
- My posts: http://127.0.0.1:8000/community/my-posts/

## Environment variables

- `SECRET_KEY` (required in production)
- `DEBUG` (default: `true`)
- `ALLOWED_HOSTS` (comma-separated, e.g. `readwoods.onrender.com`)
- `DATABASE_URL` (PostgreSQL connection string for Render)
- `DB_SSL` (default: `true` for PostgreSQL)
- `CORS_ALLOW_ALL_ORIGINS` (default: `true`)

## Render / PostgreSQL notes

1. Provision a PostgreSQL database on Render.
2. Set `DATABASE_URL` in the Render service environment to the database URL.
3. Set `SECRET_KEY`, `DEBUG=false`, and `ALLOWED_HOSTS` to your Render host.
4. Run migrations on deploy:

```bash
python manage.py migrate
```

5. Collect static files if your Render setup expects them:

```bash
python manage.py collectstatic
```

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
