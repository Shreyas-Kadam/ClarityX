# ClarityX – Product Requirements Document (PRD)

**Project Name:** ClarityX  
**Project Category:** AI-Powered Information Gap Detection Platform  
**Problem Statement:** Digital Dark Spot – AI-Assisted Information Gap Detection Platform

---

## 1. Project Overview

ClarityX is an AI-powered platform designed to identify information gaps across multiple digital sources.

When users research a topic, information is often distributed across different websites and documents. Some information may be missing, outdated, conflicting, or unverified.

Traditional search engines help users discover information, but they do not necessarily identify what information is missing or what still needs verification.

ClarityX addresses this problem by analysing information from multiple sources and generating structured research reports that highlight both available information and information gaps.

**Core Idea: Don't just tell users what you found. Tell them what you haven't found.**

## 2. Problem Statement

Digital information is growing rapidly, making it difficult to determine whether the available information is complete, accurate, current, and consistent.

Users often face the following challenges:

- Important information is missing from available sources.
- Different websites provide conflicting information.
- Information may be outdated.
- Some claims lack reliable supporting evidence.
- Users must manually compare multiple sources.
- There is no clear checklist showing what still needs verification.

ClarityX aims to reduce this research burden through AI-assisted information analysis.

## 3. Project Objectives

1. Identify missing information across multiple sources.
2. Detect outdated information using available publication or update dates.
3. Identify contradictions between different sources.
4. Highlight claims that lack sufficient supporting evidence.
5. Provide evidence and source references for identified findings.
6. Generate a verification checklist for unresolved information.
7. Maintain structured and searchable research history.

## 4. Target Users

- Students and researchers.
- Journalists and content researchers.
- Professionals conducting background research.
- Organizations comparing information from multiple sources.
- Anyone who needs to verify information before making decisions.

## 5. Core Features

### 5.1 Research Input

Users can submit a research objective and provide information through supported inputs:

- Multiple website URLs (source type: `website`).
- Pasted text content (source type: `pasted_text`).
- Document content (source type: `document`).

For the initial synchronous release, users can submit up to 5 sources per research session. External web search can be optionally enabled (`enable_search: false` by default).

### 5.2 Source Extraction

The platform extracts relevant information from submitted sources:

- Source title.
- Website URL or source label.
- Extracted text content (`extracted_content`).
- Publication or last-updated date, when available.
- Source identifier (such as S1, S2, S3).

**Extraction Policy:**
1. Attempt extraction with Trafilatura first.
2. If extraction fails or returns fewer than 100 useful characters, attempt extraction using Jina Reader.
3. Apply HTTP timeouts and record clear extraction states (`success`, `failed`, `partial`).
4. Treat all extracted website content as untrusted input.

### 5.3 Information Gap Detection

The AI analyses the collected information and categorizes findings into four core gap categories:

- **Missing Information (`missing`):** Essential information absent from available sources.
- **Outdated Information (`outdated`):** Information that may be superseded based on dates or context.
- **Conflicting Information (`conflicting`):** Direct contradictions or disagreements between sources.
- **Unverified Claims (`unverified`):** Claims lacking sufficient supporting evidence.

**Unresolved Questions:** In addition to the four gap categories, the AI identifies broader unresolved research questions. These are maintained as a distinct report section and tracked in the database as verification checklist items with `finding_id = NULL`.

### 5.4 Evidence and Citations

Each finding includes:

- Title and clear explanation.
- Gap category and severity (`low`, `medium`, `high`).
- Model-reported confidence score (0 to 1), where available.
- Narrative recommended action (`recommended_action`) advising next analytical steps.
- Supporting evidence excerpts or an explanation of missing evidence.
- Related source references (`evidence_references`).

**Evidence Integrity Rules:**
- Evidence quotes returned by the AI must be verified against the corresponding extracted source text. Unmatched or hallucinated quotes must be flagged or rejected.
- Never invent source identifiers, citations, quotations, publication dates, or evidence excerpts.

### 5.5 Conflict Detection

The platform compares claims from different sources and highlights disagreements.

It should show which sources support each conflicting claim rather than automatically assuming that one source is correct.

### 5.6 Verification Checklist

ClarityX generates actionable, stateful verification tasks:

- Tasks can be linked to specific findings or represent general unresolved research questions (`finding_id = NULL`).
- Users can review, track, and mark checklist items as completed.
- Distinct from the narrative `recommended_action` on findings, verification items are concrete, interactive to-do items.

### 5.7 Research History

Users can access previous research sessions and their generated reports.

## 6. Expected Research Report

Each completed research session should contain:

1. Research objective.
2. Sources analysed.
3. Key findings.
4. Missing information.
5. Outdated information.
6. Conflicting claims.
7. Unverified claims.
8. Evidence and citations.
9. Unresolved questions.
10. Verification checklist.

## 7. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite |
| Language | JavaScript (JSX) |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui with Base UI |
| Backend | Python + FastAPI |
| Database | Supabase PostgreSQL |
| AI Integration | OpenRouter |
| AI Models | Configurable models through OpenRouter |
| Content Extraction | Trafilatura and Jina Reader |
| Search | DuckDuckGo Search |
| Validation | Pydantic |

## 8. Functional Requirements

- FR-01: The system must accept a research objective.
- FR-02: The system must accept up to 5 information sources (types: `website`, `pasted_text`, `document`) per request.
- FR-03: The system must extract content from sources using Trafilatura, falling back to Jina Reader when useful content is under 100 characters.
- FR-04: The system must support optional automated search discovery via DuckDuckGo when enabled.
- FR-05: The system must analyse extracted information using OpenRouter AI.
- FR-06: The system must identify findings across four categories: `missing`, `outdated`, `conflicting`, and `unverified`.
- FR-07: The system must extract general unresolved research questions as a separate report section mapped to verification items with `finding_id = NULL`.
- FR-08: The system must verify that AI-extracted evidence quotes exist within the corresponding extracted source content.
- FR-09: The system must provide source references for findings.
- FR-10: The system must generate an interactive verification checklist.
- FR-11: The system must save research reports, sources, findings, evidence references, and verification items in Supabase.
- FR-12: Users must be able to retrieve, review, and delete their previous research reports.

## 9. Non-Functional Requirements

- Performance: The initial synchronous analysis API must complete within a 60-second request timeout; individual extraction and AI calls must enforce shorter granular timeouts.
- Reliability: External extraction and AI provider failures must be handled gracefully with descriptive error statuses.
- Security: API keys and Supabase service-role credentials must never be exposed in frontend code. Row Level Security must protect user data.
- Scalability: The architecture should support transitioning long-running analysis to background tasks in future versions.
- Usability: The interface should present complex findings, evidence quotes, and gaps clearly with distinct visual tags.
- Maintainability: The codebase should follow a clean service-oriented separation of concerns.
- Accuracy: AI findings must strictly trace back to verified source excerpts. Fabricating publication dates or source IDs is prohibited.

## 10. Scope and Limitations

### In Scope

- Multi-source research analysis (up to 5 sources per session for MVP).
- Website content extraction with fallback (Trafilatura $\rightarrow$ Jina Reader).
- Four-category information gap detection (`missing`, `outdated`, `conflicting`, `unverified`).
- Unresolved questions report section.
- Evidence-based findings with text-matching verification.
- Verification checklist with completion state tracking.
- Research report storage, retrieval, and deletion in Supabase.

### Out of Scope for the Initial Version

- Guaranteed verification of every claim against the open web.
- Asynchronous background worker queues (deferred to future scope).
- MCP-based integrations (optional future scope).
- Fully automated fact-checking of the entire internet.
- Real-time monitoring of websites.
- Replacement of human judgment in critical decisions.

## 11. Expected Outcome

ClarityX will provide users with a structured research report that explains:

- What information is available.
- What information is missing.
- Where sources disagree.
- Which claims need additional verification.
- What the user should investigate next.

The goal is to transform traditional information discovery into a more complete, transparent, and evidence-aware research process.

---

**Project Vision:** Help people make better-informed decisions by revealing not only what is known, but also what remains unknown.