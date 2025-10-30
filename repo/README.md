# 📦 Smart Inventory Management System

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
  <img src="https://img.shields.io/badge/PostgreSQL-15-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Bootstrap-5-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white" alt="Bootstrap" />
</div>

A modern, full-stack inventory management system with dashboards, products, suppliers, customers, sales, and purchases. Built with Flask (Python), PostgreSQL, and a responsive Bootstrap 5 UI with dark mode and charts.

## ✨ Key Features

### 🎯 Core Features
- **Clean, Responsive UI**: Landing page with login CTA, modern dashboard, mobile-friendly tables and modals
- **CRUD Modules**: Products, Suppliers, Customers, Sales, Purchases
- **Smart Reports**: Top products, low stock, sales summary with Chart.js
- **Client-Side Search & Pagination**: Instant filtering across modules
- **Form Validation**: Comprehensive HTML5 + real-time UI feedback
- **Authentication**: Simple admin login (hardcoded) with Bearer token protection
- **Dark Mode**: One-click theme toggle persisted to localStorage

### 🎨 Design Features
- **Landing Page**: Hero + features + CTA with glassmorphism accents
- **Off-Canvas Sidebar**: Optimized navigation on mobile
- **Animations**: Subtle hover/elevation for interactive elements
- **Typography**: Inter font via Google Fonts

## 🛠️ Tech Stack

### Backend
- **Framework**: [Flask](https://flask.palletsprojects.com/)
- **Database**: [PostgreSQL](https://www.postgresql.org/) (psycopg v3)
- **Auth**: Bearer token (single admin user, configurable via env)

### Frontend
- **UI**: [Bootstrap 5](https://getbootstrap.com/) + Bootstrap Icons
- **Charts**: [Chart.js](https://www.chartjs.org/)
- **Templating**: Jinja2 (`templates/index.html`, `templates/login.html`)

### Development Tools
- **Environment**: Python 3.10+
- **Package Manager**: pip
- **Version Control**: Git
- **Deployment**: Render/Heroku/Any WSGI-compatible host

## 📦 Project Structure

```
repo/
├── app.py                 # Flask app (routes, DB access, auth)
├── templates/
│   ├── index.html         # Main application UI (dashboard + modules)
│   └── login.html         # Landing page with login modal
└── (your virtualenv, configs, etc.)
```

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL (local or cloud)
- Git

### Setup

1) Clone the repository
```bash
git clone <your-repo-url>
cd Inventory-Management-System/repo
```

2) Create and activate a virtual environment
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell
# source .venv/bin/activate  # macOS/Linux
```

3) Install dependencies
```bash
pip install -r requirements.txt
# If requirements.txt is not present, install minimal deps:
pip install flask psycopg[binary] python-dotenv flask-cors
```

4) Configure environment
Create a `.env` in `repo/` (same folder as `app.py`):
```env
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Admin auth (frontend expects a bearer token after /api/login)
ADMIN_TOKEN=dev
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

5) Initialize database schema (optional helper route)
```bash
python app.py  # start server (dev)
# In another terminal, run:
curl -X POST "http://localhost:5000/admin/init-db?token=dev"
```

6) Run the app
```bash
python app.py
# App will start at http://localhost:5000/
# Visit / to see landing page, /app for the dashboard (after login)
```

## 📝 Useful Endpoints

- `POST /api/login` → returns `{ token }` for the hardcoded admin
- Protected APIs (require `Authorization: Bearer <token>`):
  - `GET/POST/PUT/DELETE /api/products`
  - `GET/POST/PUT/DELETE /api/suppliers`
  - `GET/POST/PUT/DELETE /api/customers`
  - `GET/POST /api/sales`, `GET/POST /api/purchases`
- Public reports (can be protected if desired):
  - `GET /api/reports/top-products`
  - `GET /api/reports/low-stock`
  - `GET /api/reports/sales-summary`

## 🎯 Customization

### Change Admin Credentials
Edit `.env` values: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_TOKEN`.

### Lock Down Reports
In `app.py` `@app.before_request`, remove the exception that allows public report routes.

### Tweak UI/Branding
- Update colors and typography in `templates/index.html` and `templates/login.html`.
- Replace stock images and update icons (Bootstrap Icons).

## 🌐 Deployment

Deploy on any WSGI host (Render/Heroku). Minimum steps:
1. Set `PYTHON_VERSION` and install dependencies
2. Provide environment variables (`DATABASE_URL`, `ADMIN_*`)
3. Run `gunicorn`/`waitress` with `app:app`

Example Procfile (Heroku):
```
web: gunicorn app:app --chdir repo --log-file -
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a PR with improvements (UI polish, new reports, role-based auth, etc.).

## 📞 Contact

Have questions or ideas? Open an issue in the repository.

---

<div align="center">
  <sub>Built with ❤️ using Flask, PostgreSQL, and Bootstrap 5</sub>
</div>
