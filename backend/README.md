# ClarityX – Backend Service

FastAPI REST API backend for the ClarityX Information Gap Detection Platform.

## Directory Structure

```text
backend/
├── app/
│   ├── core/           # Configuration, exceptions, security
│   ├── database/       # Supabase client and repositories
│   ├── dependencies/   # Auth and shared route dependencies
│   ├── routes/         # API endpoint routers
│   ├── schemas/        # Pydantic validation schemas
│   ├── services/       # Business logic and AI extraction services
│   └── main.py         # Application entry point and lifespan
├── tests/              # Pytest test suite
├── .env.example        # Environment variables template
├── requirements.txt    # Python dependencies
└── README.md
```

## Setup & Running

### 1. Prerequisites
- Python 3.10+
- Activated virtual environment:
  ```powershell
  cd backend
  .\venv\Scripts\Activate.ps1
  ```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 4. Start the Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
- API Root: `http://localhost:8000/`
- Health Check: `http://localhost:8000/health`
- Interactive API Docs: `http://localhost:8000/docs`

### 5. Verify Supabase Database Connectivity
Test that the backend can connect and authenticate to the Supabase platform without requiring tables to exist:
```bash
python -m app.database.supabase
```

### 6. Apply Database Migrations (Supabase Dashboard)
1. Open the [Supabase Dashboard](https://supabase.com/dashboard) and go to your project.
2. Open the **SQL Editor**.
3. Load and execute the migration script: `app/database/migrations/001_initial_schema.sql`.
4. This creates all 6 application tables, triggers (including cross-session integrity and user profile sync), indexes, and Row Level Security policies.

### 7. Run Tests
```bash
pytest
```

