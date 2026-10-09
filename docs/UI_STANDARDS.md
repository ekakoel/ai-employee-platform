# Workspace UI Standards

Use English for interface labels, user-facing messages, tooltips, documentation,
and new code comments. Format workspace dates in English. Preserve user-authored
content in its original language.

## Layout

- Keep the permanent left navigation, main workspace, and right result library.
- The right sidebar defaults to the current page's context. Keep the result
  library accessible through the Results tab, and return to page context when
  navigating elsewhere. Selected agents should scope Chat and Consult context.
- Main content owns its lists and metrics. Sidebar context must use complementary
  sources and must not repeat those lists or counters. Filter records and results
  whose titles already appear in main, including after asynchronous rendering.
- Size content grids against the main container, not the browser width.
- Use one column below 640px of main content width and two columns above it.
- Use two metric columns in compact main areas and four above 640px.
- Keep section headings unframed; cards represent individual results, work items,
  agents, metrics, or framed forms/tools.
- Avoid nested card surfaces. Items inside an existing card use flat rows.

## Tokens

- Spacing: `--space-1` (4px), `--space-2` (8px), `--space-3` (12px),
  `--space-4` (16px), and `--space-6` (24px).
- Main padding: 16px. Item card padding: 12px. Form/tool padding: 16px.
- Radius: `--radius` (8px). Borders: 1px using `--border`.
- Card surface: `--panel`, with restrained `--card-shadow`.
- Body text: 14px with 1.5 line height. Compact panel headings: 16px.
- Controls: minimum 36px height. Icon buttons: fixed 36px square.
- Checkboxes and radio controls: 16px, with their text labels adjacent.

## States

- Every workspace page, including developer pages and result preview, must define
  an English page guide in `sidebar.js`: page name, a one-sentence purpose, and
  two or three typical-use steps. Keep the purpose under 160 characters and each
  step under 140 characters. A coverage test checks every navigation entry.
- The sidebar header provides a page-specific plain-text guide download. Keep it
  available in Context and Results modes and during loading or permission errors.
  Guides are static documentation, not task data; do not add network requests.
  Keep inline sidebar content focused on complementary live records and references.

- Reserve teal for primary actions and selection; use semantic colors for status.
- Provide visible keyboard focus and labeled icon buttons.
- Let long text wrap; keep grid children at `min-width: 0`.
- Preserve loading, empty, unavailable, and disabled states.
- Inbox separates actions from work in progress, deduplicates linked tasks,
  approvals, and handoffs, and provides concise usage guidance in the sidebar.
- Inbox cards use a muted, non-overlapping watermark footer for the latest
  recorded action, actor, and local timestamp including timezone. Attribution
  comes from persisted audit events, not the assigned agent or current user.
  Distinguish missing history from unavailable history; never invent an actor.
  Keep this information on the item card rather than duplicating it in the sidebar.
- Keep dense layouts readable without shrinking text with viewport width.
- Chat uses separate framed tools for the transcript and adjacent conversation
  history. History is grouped by local activity date, then recorded owner, and
  includes title/user search. Stack the two tools in compact main containers.
  Keep saved conversations accessible, preserve drafts on switching and failure,
  and disable conversation changes during sends. Reuse returned messages rather
  than reloading the transcript after every send. Clear all cached chat state on logout.
- Message headers use tenant-scoped sender names. Human authorship comes from
  recorded message audit events, never an assumed conversation owner. Older
  messages with missing authorship display an unknown sender.
- Do not append advisory boilerplate to replies. Link only completed, nonempty,
  persisted results associated with the message and allowed by `task.read`.
  Leave the result area absent when none exists; never invent file links.
- Chat sidebar capabilities use wrapping chips in bounded scroll areas; earlier
  outputs use compact links, without repeating the transcript or its controls.
