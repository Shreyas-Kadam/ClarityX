# ClarityX

### AI-Assisted Information Gap Detection Platform

> **Don't just discover what exists. Expose what's missing.**

ClarityX is an AI-assisted research platform built for the **Digital Dark Spot** problem statement at **SHINCHAN ONLINE HACKATHON 2026**. It helps users examine information collected from multiple sources and identify potential gaps, conflicting claims, outdated details, unverified statements, and questions that still need investigation.

Rather than presenting an AI-generated summary as the complete answer, ClarityX makes the available evidence and remaining uncertainties visible so users can decide what to verify next.

---

## Overview

People use online information to make decisions about education, careers, public services, research, and business. However, relevant details are often scattered across websites and documents. Sources can disagree, become outdated, or leave important questions unanswered.

ClarityX brings source collection, extraction, AI-assisted analysis, evidence references, and verification tasks into one research workflow.

## Key Features

- **Research sessions** — create and manage research objectives and revisit previous investigations.
- **Multi-source ingestion** — add website URLs, paste research notes, or upload PDF and DOCX documents.
- **Content extraction** — extract readable website and document content for analysis, with an alternative website-reading fallback where supported.
- **AI-assisted gap detection** — organize potential findings into four categories:
  - `missing` — relevant information not found in the available sources.
  - `outdated` — information that may no longer be current.
  - `conflicting` — claims or details that appear to disagree across sources.
  - `unverified` — claims that do not have sufficient supporting evidence in the reviewed material.
- **Evidence references** — display supporting source references and quotations for findings where available.
- **Verification checklist** — turn identified gaps into tasks that users can complete and track.
- **Unresolved research questions** — keep broader questions visible when the available sources do not answer them.
- **Research summary and conclusion** — present an overview of what the reviewed material supports and what still requires validation.
- **Research history** — save and retrieve previous research sessions.

> **Important:** ClarityX is a research-assistance tool. Its findings are signals for further investigation, not guaranteed facts or a substitute for checking authoritative sources. A source that could not be accessed or extracted should not be treated as evidence that the information does not exist.

---

## Application Workflow

1. **Create a research session** — enter a clear topic, question, or research objective.
2. **Add sources** — provide website URLs, paste text, or upload supported documents.
3. **Review extracted content** — check which sources were successfully extracted and which could not be processed.
4. **Run gap analysis** — ClarityX analyzes usable source content and organizes potential findings.
5. **Inspect evidence** — open source material and review the quotations associated with findings.
6. **Verify what is missing** — use the checklist and unresolved questions to guide further research.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React, Vite, JavaScript (JSX) |
| Styling and UI | Tailwind CSS v4, shadcn/ui, Base UI, Lucide React |
| Backend | Python, FastAPI, Pydantic, Uvicorn |
| Database | Supabase, PostgreSQL |
| Authentication | Supabase Auth |
| AI integration | OpenRouter |
| Website extraction | Trafilatura, Jina Reader fallback |
| Document extraction | PDF and DOCX extraction |
| Search | DuckDuckGo Search |
| HTTP requests | HTTPX |

---

## Architecture

ClarityX uses a modular client-server architecture.

```text
                         ┌──────────────────────┐
                         │       User           │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   React + Vite UI    │
                         │   JavaScript / JSX   │
                         └──────────┬───────────┘
                                    │ REST API
                         ┌──────────▼───────────┐
                         │    FastAPI Backend   │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
     ┌────────▼────────┐  ┌─────────▼────────┐   ┌─────────▼────────┐
     │ Source Extraction│  │ AI Analysis     │   │ Search Service   │
     │ Websites/Files   │  │ OpenRouter      │   │ DuckDuckGo       │
     └─────────────────┘  └──────────────────┘   └──────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ Supabase PostgreSQL │
                         │ Research & Evidence │
                         └──────────────────────┘
```

---

## Project Structure

```text
ClarityX/
├── docs/
│   ├── PRD.md
│   ├── DESIGN.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   └── API.md
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── database/
│   │   ├── dependencies/
│   │   ├── routes/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── AGENTS.md
├── README.md
└── .gitignore
```

---

## Getting Started

### Prerequisites

Install the following before running the project:

- [Node.js](https://nodejs.org/) and npm
- Python (use a version supported by the backend dependencies)
- Git
- A Supabase project
- An OpenRouter API key

### 1. Clone the repository

Replace the repository URL below with the actual GitHub repository URL.

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd ClarityX
```

### 2. Configure the frontend

Open a terminal in the project root:

```bash
cd frontend
npm install
```

Create `frontend/.env` and add your Supabase public project configuration:

```env
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
```

If your Supabase project uses the legacy anon key, the frontend also supports:

```env
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

Start the frontend development server:

```bash
npm run dev
```

Frontend URL: [http://localhost:5173](http://localhost:5173)

### 3. Configure the backend

Open a second terminal from the project root:

```bash
cd backend
python -m venv venv
```

Activate the virtual environment on Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Create `backend/.env` using the provided `.env.example` as the reference. Add the required Supabase and OpenRouter configuration values from your own accounts. Keep all secrets in the backend environment.

Start the backend:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URL: [http://127.0.0.1:8000](http://127.0.0.1:8000)

FastAPI interactive API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Environment and Security

- Do not commit `frontend/.env` or `backend/.env`.
- Never expose the Supabase service-role key or OpenRouter API key in frontend code.
- Use only the Supabase publishable/anon key in the browser.
- Keep backend secrets in environment variables.
- Apply Supabase Row Level Security (RLS) to user-owned data.
- Treat extracted website and document content as untrusted input.
- URL fetching must retain SSRF and unsafe-redirect protections.
- Do not commit credentials, virtual environments, or generated build files.

---

## Documentation

The `docs/` directory contains the deeper project documentation:

| File | Description |
|---|---|
| `docs/PRD.md` | Product requirements and feature scope |
| `docs/DESIGN.md` | UI/UX design guidelines |
| `docs/ARCHITECTURE.md` | System architecture and service responsibilities |
| `docs/DATABASE.md` | Database schema and relationships |
| `docs/API.md` | API endpoints and request/response formats |
| `AGENTS.md` | Instructions and development conventions for AI coding agents |

---

## Current Scope and Limitations

- Analysis depends on the quality, relevance, and extractability of the supplied sources.
- Some websites may block automated access. When extraction is blocked, users may need to upload the document or provide its text instead.
- AI-generated findings can be incomplete or incorrect and should be checked against the cited source material.
- A missing result in the collected sources does not prove that the information does not exist elsewhere.
- The project should not be treated as a replacement for expert review or authoritative verification.

---

## Future Scope

Potential directions for further development include:

- More source types and extraction options.
- Deeper source reliability and freshness analysis.
- Background processing for longer research sessions.
- Research report export and sharing.
- Real-time progress updates.
- Scheduled source monitoring.
- Additional AI providers and integrations.

---

## Hackathon

**Event:** SHINCHAN ONLINE HACKATHON 2026  
**Official Problem Statement:** DIGITAL DARK SPOT  
**Challenge:** AI-Assisted Information Gap Detection Platform  
**Participation:** Individual

ClarityX was developed as a solution to the challenge of identifying potential information gaps, conflicting claims, outdated details, and unanswered questions across multiple sources.

---

## Acknowledgements

Developed as part of SHINCHAN ONLINE HACKATHON 2026. Thanks to the organizers for the opportunity to learn, build, and experiment.

---

## License

No license has been specified yet. If you intend to make this repository open source, add a suitable `LICENSE` file before presenting it as reusable open-source software.

---

**ClarityX — Don't just tell users what you found. Tell them what you haven't found.**
