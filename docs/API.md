# ClarityX – API Documentation

## 1. API Overview

ClarityX uses REST APIs built with Python and FastAPI.

The APIs allow the React frontend to communicate with the backend for research analysis, source extraction, report retrieval, and verification checklist management.

### Base URL

Development:

`http://localhost:8000`

API prefix:

`/api`

### Request and Response Format

- Request format: JSON
- Response format: JSON
- Authentication: Supabase JWT for protected endpoints.
- API documentation: `/docs`
- Alternative API documentation: `/redoc`

## 2. API Endpoints Overview

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/` | Welcome message | No |
| GET | `/health` | Backend health check | No |
| POST | `/api/research/analyze` | Start research analysis | Yes |
| GET | `/api/research` | Retrieve research history | Yes |
| GET | `/api/research/{id}` | Retrieve a research report | Yes |
| DELETE | `/api/research/{id}` | Delete a research report | Yes |
| POST | `/api/sources/extract` | Extract website content | Yes |
| PATCH | `/api/verification/{id}` | Update checklist status | Yes |

Protected endpoints require an authenticated Supabase user session from the start. Access tokens are passed via the standard `Authorization: Bearer <token>` header.

## 3. General Response Structure

### Successful Response

Responses should return the relevant data and a consistent success indicator.

Example:

```json
{
  "success": true,
  "message": "Request completed successfully",
  "data": {}
}
```

### Error Response

```json
{
  "success": false,
  "message": "An error occurred",
  "detail": "Detailed error information"
}
```

Do not expose internal stack traces, secrets, or sensitive implementation details in production responses.

## 4. Health Check APIs

### 4.1 Root Endpoint

**GET** `/`

Purpose: Confirm that the backend server is running.

Example response:

```json
{
  "message": "Welcome to ClarityX API"
}
```

### 4.2 Health Endpoint

**GET** `/health`

Purpose: Check the backend health.

Example response:

```json
{
  "status": "healthy",
  "project": "ClarityX"
}
```

## 5. Research APIs

### 5.1 Start Research Analysis

**POST** `/api/research/analyze`

Purpose: Start an information gap analysis.

Request limits and options:
- **Maximum Sources:** Up to 5 sources per research session for the synchronous MVP.
- **Request Timeout:** 60 seconds overall timeout (external extraction and AI calls enforce shorter granular timeouts).
- **Source Types:** `website` (or alias `url`), `pasted_text`, and `document`.
- **Search Toggle:** Optional `enable_search` boolean (defaults to `false`).

Request body:

```json
{
  "research_goal": "Analyse the latest scholarship information",
  "sources": [
    {
      "type": "website",
      "value": "https://example.com/scholarship"
    },
    {
      "type": "pasted_text",
      "value": "Eligible applicants must submit transcripts before the deadline..."
    }
  ],
  "enable_search": false
}
```

Expected response:

```json
{
  "success": true,
  "message": "Research analysis completed",
  "data": {
    "research_id": "123e4567-e89b-12d3-a456-426614174000",
    "research_goal": "Analyse the latest scholarship information",
    "status": "completed",
    "summary": "Summary of the analysed information and identified gaps",
    "findings": [
      {
        "id": "223e4567-e89b-12d3-a456-426614174001",
        "category": "missing",
        "title": "Application deadline not specified",
        "description": "Neither source specifies the final date for submitting applications.",
        "severity": "high",
        "confidence": 0.92,
        "recommended_action": "Check the university registrar page or official contact for deadline confirmation.",
        "evidence_references": [
          {
            "id": "323e4567-e89b-12d3-a456-426614174002",
            "source_id": "423e4567-e89b-12d3-a456-426614174003",
            "source_code": "S1",
            "evidence_text": "Scholarships will be awarded for the upcoming academic year.",
            "evidence_type": "contextual"
          }
        ]
      }
    ],
    "sources": [
      {
        "id": "423e4567-e89b-12d3-a456-426614174003",
        "source_code": "S1",
        "title": "Scholarship Overview",
        "url": "https://example.com/scholarship",
        "source_type": "website",
        "content_preview": "Scholarships will be awarded for the upcoming academic year. Eligibility criteria include...",
        "published_at": "2026-01-15T00:00:00Z",
        "extraction_status": "success"
      }
    ],
    "unresolved_questions": [
      {
        "id": "523e4567-e89b-12d3-a456-426614174004",
        "task": "What is the official GPA cutoff for international applicants?",
        "status": "pending"
      }
    ],
    "verification_items": [
      {
        "id": "623e4567-e89b-12d3-a456-426614174005",
        "finding_id": "223e4567-e89b-12d3-a456-426614174001",
        "task": "Contact admissions department to verify application deadline",
        "status": "pending",
        "created_at": "2026-10-31T12:00:00Z",
        "completed_at": null
      }
    ]
  }
}
```

Notes on payload structure:
- **Findings:** Strictly categorized into `missing`, `outdated`, `conflicting`, `unverified`. Contains narrative guidance in `recommended_action`.
- **Evidence Verification:** Excerpts in `evidence_references` must be validated against the source's extracted text. Unmatched quotes are flagged or rejected.
- **Large Content Excluded:** Full `extracted_content` is omitted from normal report payloads; a truncated `content_preview` is returned to maintain low latency.
- **Unresolved Questions:** Captured in their own report section while stored in `verification_items` with `finding_id = NULL`.
- **Execution Model:** Initial analysis runs synchronously within 60 seconds; longer research workflows may transition to background tasks in future versions.

### 5.2 Retrieve Research History

**GET** `/api/research`

Purpose: Retrieve the authenticated user's previous research sessions.

Optional query parameters:

- `limit`: Maximum number of records.
- `offset`: Number of records to skip.
- `status`: Filter by research status.

Example:

`GET /api/research?limit=10&offset=0`

Expected response:

```json
{
  "success": true,
  "data": {
    "research_sessions": [
      {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "research_goal": "Analyse the latest scholarship information",
        "status": "completed",
        "sources_count": 2,
        "findings_count": 4,
        "created_at": "2026-10-31T12:00:00Z",
        "updated_at": "2026-10-31T12:00:00Z"
      }
    ],
    "total": 1
  }
}
```

### 5.3 Retrieve a Research Report

**GET** `/api/research/{id}`

Purpose: Retrieve a particular research report.

Example:

`GET /api/research/123e4567-e89b-12d3-a456-426614174000`

Expected response:

```json
{
  "success": true,
  "data": {
    "research_id": "123e4567-e89b-12d3-a456-426614174000",
    "research_goal": "Analyse the latest scholarship information",
    "status": "completed",
    "summary": "Summary of the analysed information and identified gaps",
    "findings": [
      {
        "id": "223e4567-e89b-12d3-a456-426614174001",
        "category": "missing",
        "title": "Application deadline not specified",
        "description": "Neither source specifies the final date for submitting applications.",
        "severity": "high",
        "confidence": 0.92,
        "recommended_action": "Check the university registrar page or official contact for deadline confirmation.",
        "evidence_references": [
          {
            "id": "323e4567-e89b-12d3-a456-426614174002",
            "source_id": "423e4567-e89b-12d3-a456-426614174003",
            "source_code": "S1",
            "evidence_text": "Scholarships will be awarded for the upcoming academic year.",
            "evidence_type": "contextual"
          }
        ]
      }
    ],
    "sources": [
      {
        "id": "423e4567-e89b-12d3-a456-426614174003",
        "source_code": "S1",
        "title": "Scholarship Overview",
        "url": "https://example.com/scholarship",
        "source_type": "website",
        "content_preview": "Scholarships will be awarded for the upcoming academic year. Eligibility criteria include...",
        "published_at": "2026-01-15T00:00:00Z",
        "extraction_status": "success"
      }
    ],
    "unresolved_questions": [
      {
        "id": "523e4567-e89b-12d3-a456-426614174004",
        "task": "What is the official GPA cutoff for international applicants?",
        "status": "pending"
      }
    ],
    "verification_items": [
      {
        "id": "623e4567-e89b-12d3-a456-426614174005",
        "finding_id": "223e4567-e89b-12d3-a456-426614174001",
        "task": "Contact admissions department to verify application deadline",
        "status": "pending",
        "created_at": "2026-10-31T12:00:00Z",
        "completed_at": null
      }
    ]
  }
}
```

The backend must verify that the requested report belongs to the authenticated user.

### 5.4 Delete a Research Report

**DELETE** `/api/research/{id}`

Purpose: Delete a research session and its dependent records.

Expected response:

```json
{
  "success": true,
  "message": "Research deleted successfully"
}
```

Deletion must respect database ownership policies and cascading foreign-key relationships.

## 6. Source APIs

### 6.1 Extract Website Content

**POST** `/api/sources/extract`

Purpose: Extract information from a submitted website URL.

Extraction policy:
1. Attempt extraction with Trafilatura first.
2. If extraction fails or returns fewer than 100 useful characters, attempt Jina Reader.
3. Content is treated as untrusted input and protected against SSRF.

Request body:

```json
{
  "url": "https://example.com/article"
}
```

Expected response:

```json
{
  "success": true,
  "data": {
    "title": "Example Article",
    "url": "https://example.com/article",
    "source_type": "website",
    "extracted_content": "Extracted text content from the article...",
    "published_at": null,
    "extraction_status": "success"
  }
}
```

If extraction fails, return a meaningful error without exposing internal details.

## 7. Verification APIs

### 7.1 Update Verification Checklist

**PATCH** `/api/verification/{id}`

Purpose: Update the completion status of a verification item.

Request body:

```json
{
  "status": "completed"
}
```

Expected response:

```json
{
  "success": true,
  "message": "Verification item updated successfully",
  "data": {
    "id": "uuid",
    "status": "completed"
  }
}
```

Allowed statuses:

- pending
- completed

The backend must verify ownership before updating an item.

## 8. HTTP Status Codes

| Status Code | Meaning |
|---|---|
| 200 | Successful request (including deletion returning a response body) |
| 201 | Resource created |
| 202 | Request accepted for processing |
| 204 | Successful request with no response body |
| 400 | Invalid request |
| 401 | Authentication required or invalid |
| 403 | Access denied |
| 404 | Resource not found |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 502 | External service failure |
| 503 | Service temporarily unavailable |

## 9. Authentication

Protected APIs use Supabase Authentication from the beginning.

The frontend sends an access token in the Authorization header:

```http
Authorization: Bearer YOUR_SUPABASE_ACCESS_TOKEN
```

FastAPI verifies access tokens through Supabase Auth using the official Supabase Python client (`supabase.auth.get_user(token)`).

Token verification must support the project's configured JWT signing method (and `SUPABASE_JWT_SECRET` is not required for the initial implementation).

The backend must never trust a user ID supplied in the request body as proof of ownership.

The Supabase service-role key must never be exposed to the frontend.

## 10. API Security

- Validate every incoming request.
- Verify authentication tokens on protected endpoints.
- Apply ownership checks to research resources.
- Keep API credentials in environment variables.
- Restrict CORS to trusted origins.
- Apply request size and rate limits.
- Validate URLs before fetching external content.
- Protect against SSRF and unsafe redirects.
- Avoid exposing stack traces in production.
- Use consistent error responses.

## 11. API Testing

APIs should be tested using:

- FastAPI Swagger UI (`/docs`).
- Postman or equivalent API testing tools.
- Automated tests using pytest and HTTPX.

Each endpoint should be tested for:

- Valid requests.
- Missing fields.
- Invalid input.
- Unauthorized access.
- Database failures.
- External service failures.
- Correct response structure.

## 12. Future API Improvements

Possible future endpoints:

- Research report export.
- Source reliability analysis.
- Additional document uploads.
- Research progress tracking.
- Saved report sharing.
- Search within research history.

These should be introduced only when needed.

## 13. API Design Objective

The APIs should provide a consistent and secure communication layer between the frontend, backend services, AI provider, and Supabase database.

**API Vision:** Every research operation should be accessible through clear, predictable, and well-documented endpoints.