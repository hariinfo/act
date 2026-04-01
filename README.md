# ACT Practice Test App

A full-stack application for practicing ACT tests. Upload ACT practice test PDFs, take timed tests, and review results.

## Tech Stack

- **Backend:** Python / FastAPI / SQLAlchemy / PostgreSQL
- **Frontend:** React 19 / Vite / React Router
- **LLM (optional):** Ollama (local) for topic classification and answer explanations

## Quick Start with Docker

The easiest way to run the full stack:

```bash
# Clone and start
cp .env.example .env        # edit if needed
docker compose up --build
```

This starts:
- **PostgreSQL** on port 5432
- **Backend API** on port 8000
- **Frontend** on port 3000

Open http://localhost:3000 to use the app.

## Manual Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL

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

# Start the backend
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

## Environment Variables

| Variable | Description | Default | Required |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/act_test_db` | Yes |
| `SECRET_KEY` | JWT signing key | (change in production) | Yes |
| `ANTHROPIC_API_KEY` | Anthropic API key | (empty) | No |
| `VITE_API_URL` | Backend API URL for frontend | `http://localhost:8000/api` | No |
| `APP_URL` | Public URL of the app (for email links) | `http://localhost:3000` | No |
| `SMTP_HOST` | SMTP server for sending emails | `smtp.gmail.com` | No |
| `SMTP_PORT` | SMTP port | `587` | No |
| `SMTP_USER` | SMTP username | (empty) | No |
| `SMTP_PASSWORD` | SMTP password | (empty) | No |

## AI-Powered Features (Optional)

The app can optionally use a local LLM to:

- **Classify questions by topic** (e.g. "Grammar & Usage", "Algebra", "Data Interpretation")
- **Generate step-by-step explanations** for each question's correct answer

These features are **completely optional**. The core functionality (PDF upload, test taking, scoring) works without any LLM. You can skip topic classification and explanation generation during PDF upload.

### Using Ollama (fully local, no API key needed)

The app uses [Ollama](https://ollama.ai) with the `deepseek-r1:8b` model by default. This runs entirely on your machine with no external API calls.

**1. Install Ollama:**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai/download
```

**2. Pull the model:**

```bash
ollama pull deepseek-r1:8b
```

**3. Start Ollama:**

```bash
ollama serve
```

Ollama runs on `http://localhost:11434` by default. The app connects to it automatically.

**Using a different Ollama model:**

To use a different model, edit the `OLLAMA_MODEL` variable in:
- `backend/app/topic_classifier.py`
- `backend/app/explanation_generator.py`

**Docker with Ollama:**

If running via Docker, Ollama must be accessible from the backend container. If Ollama runs on the host machine, use `host.docker.internal` instead of `localhost`:

```bash
# In backend/app/topic_classifier.py and explanation_generator.py
OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
```

Or run Ollama as a Docker service alongside the app (add to `docker-compose.yml`):

```yaml
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
```

Then point `OLLAMA_URL` to `http://ollama:11434/api/generate`.

### Using Anthropic API (cloud)

If you prefer cloud-based AI, set the `ANTHROPIC_API_KEY` environment variable. Note that the current implementation uses Ollama by default; to switch to Anthropic, you would modify the topic classifier and explanation generator to use the Anthropic SDK.

## Usage

1. Open the app and create an admin account at `/api/admin/create-admin`.
2. Log in and go to the Admin dashboard.
3. Click **Seed Subjects** to initialize the subject categories.
4. **Upload** an ACT practice test PDF — the app parses sections, questions, passages, and answer keys automatically.
5. **Create a test** from the uploaded question bank.
6. Students log in, take timed tests, and review results with score breakdowns.
