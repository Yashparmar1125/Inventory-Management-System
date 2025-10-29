# Smart Inventory Management System

## Prerequisites
- Python 3.10+
- MySQL 8+

## Setup
1. Create database and objects:
   - Import `repo/schema.sql` into MySQL (e.g., via MySQL Workbench or CLI).
2. Create a virtual environment and install deps:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r repo/requirements.txt
   ```
3. Configure environment variables (create `.env` in `repo/` or export env vars). For Render PostgreSQL, prefer `DATABASE_URL`:
   ```ini
   # Render example
   DATABASE_URL=postgres://<user>:<password>@<host>:<port>/<db>

   # Local fallback (used only if DATABASE_URL is not set)
   DB_HOST=localhost
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_NAME=postgres
   FLASK_DEBUG=1
   ```

## Run
```bash
python repo/app.py
```
Open `http://localhost:5000` in your browser.

## PostgreSQL Schema
- Use `repo/schema_postgres.sql` on PostgreSQL (Render). It defines identity columns and an update trigger for `UpdatedAt`.

## Notes
- Health check at `/health`.
- All API routes under `/api/...`.
- For production, set proper DB credentials and consider running behind a WSGI server (gunicorn/uwsgi) with a reverse proxy (Nginx), and self-host static assets to enable a strict CSP.
