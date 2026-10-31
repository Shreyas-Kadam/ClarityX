# ClarityX – UI/UX Design Document

## 1. Design Overview

ClarityX is an AI-powered Information Gap Detection Platform.

The interface should communicate intelligence, clarity, reliability, and transparency.

The design should make complex research findings easy to understand without overwhelming the user.

**Design principle:** Clean, modern, professional, and data-focused.

## 2. Design Goals

- Provide a simple and intuitive research experience.
- Make information gaps visually distinguishable.
- Present evidence and source references clearly.
- Highlight conflicting and outdated information.
- Make research reports easy to scan.
- Maintain a consistent visual language across the application.
- Ensure responsive layouts for desktop, tablet, and mobile.

## 3. Visual Theme

The application should use a modern AI research dashboard style.

### Theme Characteristics

- Dark-first interface.
- Clean layouts with sufficient spacing.
- Subtle borders and shadows.
- Rounded cards and containers.
- Clear typography hierarchy.
- Minimal and meaningful animations.
- Consistent icon usage.

Avoid excessive gradients, unnecessary animations, and overly decorative elements.

## 4. Colour System

Use the following initial colour palette. These values can be adjusted during implementation.

| Purpose | Colour | Hex |
|---|---|---|
| Main background | Deep Navy | #0B1020 |
| Secondary background | Dark Blue | #111827 |
| Card background | Slate | #172033 |
| Primary accent | Cyan | #22D3EE |
| Secondary accent | Blue | #3B82F6 |
| Primary text | White | #F8FAFC |
| Secondary text | Slate Grey | #94A3B8 |
| Success | Green | #22C55E |
| Warning | Amber | #F59E0B |
| Error / Conflict | Red | #EF4444 |
| Border | Dark Slate | #334155 |

### Status Colour Usage

- Missing information: Amber.
- Outdated information: Orange.
- Conflicting information: Red.
- Unverified information: Purple.
- Verified checklist item: Green.

Colours must always be accompanied by readable labels or icons so users do not rely on colour alone.

## 5. Typography

Use a modern sans-serif font.

Recommended font: Geist.

### Typography Hierarchy

- Main page headings: Large and bold.
- Section headings: Medium and semibold.
- Card titles: Medium and semibold.
- Body text: Regular.
- Metadata: Smaller and muted.
- Evidence excerpts: Readable with clear separation from surrounding content.

Maintain consistent font sizes and line heights.

## 6. Main Application Layout

The application should have the following main areas:

### 6.1 Sidebar Navigation

The sidebar provides access to:

- Dashboard.
- New Research.
- Research History.
- Saved Reports.
- Settings.

The sidebar should be collapsible on desktop and accessible through a navigation drawer on smaller screens.

### 6.2 Top Navigation Bar

The top navigation should contain:

- ClarityX branding.
- Current page title or breadcrumb.
- User profile or account menu.
- Relevant page actions.

### 6.3 Main Content Area

The main content area should display the active page.

Use consistent content width, spacing, card layouts, and responsive behaviour.

## 7. Main Screens

### 7.1 Dashboard

Purpose: Give users an overview of their research activity.

Expected elements:

- Welcome heading.
- New Research action.
- Total research sessions.
- Total sources analysed.
- Identified information gaps.
- Recent research reports.
- Quick access to previous work.

### 7.2 New Research Workspace

Purpose: Allow users to initiate an information gap analysis.

Expected elements:

- Research objective input.
- Multiple source input fields (up to 5 sources for MVP: `website` URL, `pasted_text`, `document`).
- Optional DuckDuckGo search discovery toggle.
- Add/remove source controls.
- Start Analysis button.
- Loading and processing states (with 60s timeout handling).
- Input validation and error messages.

Keep the research submission process simple.

### 7.3 Analysis Results

Purpose: Present the research report.

Expected elements:

- Research objective.
- Overall analysis summary.
- Sources analysed (with metadata and truncated content preview).
- Information gap overview across the 4 categories (`missing`, `outdated`, `conflicting`, `unverified`).
- Finding cards with evidence excerpts and source tags.
- Clickable source references.
- Unresolved questions section (general open questions).
- Verification checklist (interactive, stateful task items).

### 7.4 Finding Cards

Each finding card should display:

- Finding title.
- Finding category badge (`missing`, `outdated`, `conflicting`, `unverified`).
- Explanation of the gap.
- Severity (`low`, `medium`, `high`) and model confidence score (0 to 1).
- Related source references (e.g. S1, S2).
- Supporting or contextual evidence quotes (verified against source content) or reason evidence is missing.
- Narrative recommended next step (`recommended_action`).

### 7.5 Conflict Comparison

When sources disagree, show:

- Claim from Source A.
- Claim from Source B.
- Source references.
- Explanation of the disagreement.

Do not automatically label a source as correct without sufficient evidence.

### 7.6 Unresolved Questions & Verification Checklist

- **Unresolved Questions:** Displayed in a distinct section highlighting broad unknowns and open research avenues (`verification_items` with `finding_id = NULL`).
- **Verification Checklist:** Actionable, checkable tasks (both finding-specific actions and unresolved question follow-ups) that users can mark pending or completed.

### 7.7 Research History

Purpose: Allow users to revisit previous research sessions.

Expected elements:

- Research title or objective.
- Creation date.
- Number of sources.
- Number of findings.
- Analysis status.
- Open report action.

### 7.8 Settings

Expected elements:

- User account details.
- Authentication-related settings.
- Preferences.
- Sign-out action.

## 8. Reusable UI Components

Use reusable components wherever possible.

Suggested components:

- Sidebar.
- Navbar.
- DashboardCard.
- ResearchInput.
- SourceInput.
- SourceCard.
- FindingCard.
- EvidenceCard.
- ConflictCard.
- VerificationChecklist.
- StatusBadge.
- LoadingState.
- EmptyState.
- ErrorState.
- ConfirmationDialog.

Use shadcn/ui with the selected Base UI component library and Lucide icons.

## 9. Interaction Design

- Buttons must provide clear hover, active, and disabled states.
- Forms must provide meaningful validation feedback.
- Long-running analysis must show a loading or progress state.
- Users must be able to open source links.
- Finding cards should allow users to inspect supporting evidence.
- Verification checklist items should be interactive.
- Empty states should explain what the user can do next.
- Errors should be understandable and actionable.

## 10. Responsive Design

### Desktop

- Full sidebar navigation.
- Multi-column dashboard layouts.
- Side-by-side source comparisons where appropriate.

### Tablet

- Compact navigation.
- Reduced column count.
- Flexible card layouts.

### Mobile

- Collapsible navigation.
- Single-column layouts.
- Readable evidence sections.
- Touch-friendly controls.
- Responsive tables or alternative card layouts.

## 11. Accessibility

- Use semantic HTML elements.
- Maintain readable colour contrast.
- Provide labels for form fields.
- Support keyboard navigation.
- Provide accessible button names.
- Do not use colour as the only indicator of status.
- Maintain visible focus indicators.

## 12. Design Consistency Rules

1. Use the same spacing scale throughout the application.
2. Reuse components instead of duplicating UI code.
3. Maintain consistent border radius and typography.
4. Use animations only when they improve understanding.
5. Avoid unnecessary visual clutter.
6. Keep evidence and source references easy to locate.
7. Clearly distinguish AI-generated findings from verified facts.

## 13. Design Objective

The final interface should feel like a professional AI research workspace where users can investigate information, understand uncertainty, compare evidence, and identify what still needs verification.

**Design Vision:** Make the unknown visible and make research more transparent.