# AGENTS.md

## Agent Overview

**ghcpsdknotify** is a *Personal AI Daily Briefing Agent* — a Windows desktop application that analyzes a user's local Markdown notes and delivers two AI-driven features on a configurable schedule:

| Feature | Purpose | Tools Used |
|---------|---------|------------|
| **Feature A — Daily Briefing** | Retrieve the latest news, technical updates, and internal knowledge related to topics found in the user's notes | Bing Web Search (SDK built-in) + WorkIQ MCP (optional) |
| **Feature B — Review Quiz** | Generate spaced-repetition quizzes (Q1: multiple-choice, Q2: free-form) from note content, then auto-score answers via a separate LLM session | None (local files only) |
| **Quiz Scoring** | Evaluate user answers against source material and return structured JSON results | None |

The agent runs as a system-tray resident app — scheduled jobs invoke the GitHub Copilot SDK, produce Markdown output, and deliver Windows toast notifications linking to an HTML viewer.

---

## Architecture

```
Local Markdown Files
        │
        ▼
┌──────────────┐     ┌─────────────────────┐
│ Folder Scanner│────▶│ File Selector        │
│ (scan_folders)│     │ (weighted random +   │
└──────────────┘     │  discovery rotation) │
                      └─────────┬───────────┘
                                │
                                ▼
                      ┌─────────────────────┐
                      │ Prompt Builder       │
                      │ (system + user       │
                      │  prompt templates)   │
                      └─────────┬───────────┘
                                │
                                ▼
                      ┌─────────────────────┐
                      │ Copilot SDK Session  │──── Bing Web Search (built-in)
                      │ (CopilotClientWrapper│──── WorkIQ MCP (stdio, optional)
                      │  w/ retry + timeout) │
                      └─────────┬───────────┘
                                │
                                ▼
                      ┌─────────────────────┐
                      │ Output Writer        │──▶ Markdown file
                      │ + Toast Notification │──▶ Windows notification → HTML Viewer
                      └─────────────────────┘
```

### SDK Integration

- **Package**: `copilot` (GitHub Copilot SDK for Python)
- **Default model**: `claude-sonnet-4.6` (configurable in `config.yaml`)
- **System message mode**: `replace` — system prompt fully overrides default behavior
- **Session lifecycle**: One session per feature execution; created → `send_and_wait` → destroyed
- **Error strategy**: Exponential back-off retry (5 s → 15 s → 45 s, max 3 attempts)
- **Timeout**: 120 s per SDK call (configurable), plus 30 s margin for retry wrapper

---

## System Prompts

### Feature A — Daily Briefing

> *"You are a Personal AI Daily Briefing Agent."*

The system prompt instructs the model to:

1. Analyze the user's Markdown files provided in the user prompt
2. Search for the latest news, technical updates, blog posts, and internal knowledge on each topic
3. Produce a Markdown summary with `##` headings, source URLs, and omit empty sections
4. Target a length readable in 5 minutes

The prompt dynamically injects **tool routing rules** (see next section) depending on whether WorkIQ MCP is enabled.

**Source**: `app/main.py` — `SYSTEM_PROMPT_A_BASE` / `SYSTEM_PROMPT_A_BASE_EN`

### Feature B — Review Quiz

> *"You are a Personal AI Daily Briefing Agent."*

The system prompt instructs the model to:

1. Analyze the user's Markdown files, considering each file's last-modified date
2. Select **one topic** per run and generate exactly **2 questions** (Q1: 4-choice, Q2: free-form)
3. Alternate quiz patterns per execution:
   - **Odd runs** — *Active Learning*: pick recently updated notes (1–2 weeks), higher difficulty
   - **Even runs** — *Review*: pick older notes (1+ month), basic-to-moderate difficulty
4. Insert `<!-- topic_key: ... -->` HTML comments for spaced-repetition tracking
5. **Never include answers** — scoring is done in a separate session

**Source**: `app/main.py` — `SYSTEM_PROMPT_B_TEMPLATE` / `SYSTEM_PROMPT_B_TEMPLATE_EN`

### Quiz Scoring

A dedicated session with the system prompt:

> *"You are a quiz scoring system. Output only JSON in the specified format."*

The scoring prompt provides source material, questions, and user answers. The model returns a JSON object:

```json
{
  "q1_correct": true,
  "q1_correct_answer": "B",
  "q1_explanation": "...",
  "q2_evaluation": "good | partial | poor",
  "q2_feedback": "..."
}
```

**Source**: `app/quiz_scorer.py` — `_SCORING_PROMPT_TEMPLATE_EN`

### Language Switching

All prompts have **Japanese (ja)** and **English (en)** variants. The active language is determined by `config.yaml → language` and resolved at runtime via `_get_prompt(ja, en)`. The `app/i18n.py` module provides a 450-line translation catalog for all UI strings.

---

## Tool Routing Rules

The agent uses **system-prompt-level instructions** to guide the LLM on which tools to invoke. These rules are embedded in the Feature A system prompt.

### Bing Web Search (SDK Built-in)

Used automatically by the Copilot SDK when the model decides web search is needed. The system prompt directs the model to use it for:

- Technology names, product names, OSS project names — latest information
- Official documentation, blogs, release notes
- Industry news and trends

### WorkIQ MCP (Optional, stdio)

Connected as an MCP server when `config.yaml → workiq_mcp.enabled: true`:

```python
mcp_servers = {
    "workiq": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@microsoft/workiq", "mcp"],
        "tools": ["*"],
    },
}
```

The system prompt directs the model to use WorkIQ for:

- Internal project names, customer names, team names
- Internal case studies, templates, knowledge articles
- Internal announcements and discussions

### Routing Decision Logic

| Condition | Action |
|-----------|--------|
| Topic is a public technology / product / OSS | Use Bing |
| Topic mentions internal projects / customers / teams | Use WorkIQ MCP |
| Uncertain which tool to use | Search with **both** tools |
| WorkIQ returns no results | Omit that section silently |
| Feature B (quiz generation) | **No tools** — works from local file content only |
| Quiz Scoring | **No tools** — evaluates from provided context only |

---

## Spaced Repetition

Quiz results feed into a simplified SM-2 algorithm (Level 0–5):

| Result | Level Change |
|--------|-------------|
| Q1 correct + Q2 "good" | Level + 1 (max 5) |
| Q2 "partial" | Level unchanged |
| Q1 wrong or Q2 "poor" | Reset to Level 0 |

Intervals: 1 → 3 → 7 → 14 → 30 → 60 days. State is persisted in `settings/state.json`.

---

## Responsible AI Considerations

- **Local-only file access**: The agent reads Markdown files from user-configured local folders. Files are never uploaded or transmitted externally — only their text content is included in prompts sent via the Copilot SDK.
- **SDK data protection**: All LLM communication goes through the GitHub Copilot SDK, which is governed by the GitHub Copilot data protection policies (no prompt/response retention for model training under business/enterprise plans).
- **No PII collection**: The agent does not collect, store, or transmit personally identifiable information. Only file paths and note content appear in prompts.
- **Transparent scoring**: Quiz scoring results (JSON) are stored locally in `settings/state.json`. Users can inspect and delete this data at any time.
- **User control**: All features (scheduling, WorkIQ integration, language) are configurable via `settings/config.yaml` or the built-in Settings UI. Users can disable any feature or adjust schedules freely.
