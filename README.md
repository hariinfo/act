# ACT Practice Test App

A full-stack application for practicing ACT tests. Upload ACT practice test PDFs, take timed tests, and review results.

## Tech Stack

- **Backend:** Python / FastAPI / SQLAlchemy / PostgreSQL
- **Frontend:** React 19 / Vite / React Router

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL

## Setup

### 1. Database

Create a PostgreSQL database:

```sql
CREATE DATABASE act_test_db;
```

### 2. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials and secret key
```

#### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/act_test_db` |
| `SECRET_KEY` | JWT signing key | (change in production) |
| `ANTHROPIC_API_KEY` | API key for AI-powered explanations | (optional) |

#### Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000. API docs at http://localhost:8000/docs.

### 3. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The app will be available at http://localhost:3000.

## Usage

1. Register an account and log in.
2. Upload an ACT practice test PDF via the admin panel.
3. Take a practice test and review your results.
