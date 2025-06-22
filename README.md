# NoticeHub

NoticeHub automates the flow from incoming maintenance or outage e-mails to internal notifications. The
pipeline fetches e‑mails, uses an LLM to extract structured facts, stores the results in a database and
identifies which internal systems are affected. The Streamlit dashboard provides a UI for reviewing
notifications and managing dependencies.

## Work log

The table below summarises the originally planned effort and the approximate time actually spent on each
work package (WP). The *Interim Report* dated **19 May 2025** marked WP1–WP4 as finished and WP5 half done.
Final completion was on **22 June 2025**.

| WP | Scope                                   | Planned h | Actual h |
| -- | --------------------------------------- | --------: | -------: |
| 1  | Set‑up, tooling, LLM basics             | 15        | 14       |
| 2  | E‑mail integration & pre‑filter         | 10        | 12       |
| 3  | LLM information extraction              | 35        | 35       |
| 4  | DB design & implementation              | 20        | 18       |
| 5  | Dependency analysis logic               | 15        | 20       |
| 6  | Notification generation                 | 20        | 18       |
| 7  | System integration / orchestration      | 10        | 15       |
| 8  | Tests, error handling, validation       | 15        | 17       |
| 9  | Documentation & final report            | 10        | 12       |
| **Total** |                                   | **150**   | **161**  |

A chronological log of commits is available using `git log`. Example:

```
$ git log --pretty=format:'%ad - %h - %s' --date=short
2025-06-22 - 28f7b33 - Add downtime event tracking and statistics functionality
...
```

## Problems & solutions

- **LLM hallucinated service names** – fixed by running multiple extraction rounds and choosing the most
  common result.
- **E‑mail pre‑filter too strict** – added configurable whitelists/blacklists in `.env` so false negatives can
  be tuned.
- **Updating demo data mixed real entries** – the dashboard now only fetches data from the API and stores
  edits back to the server.
- **Deployment confusion** – Docker Compose definitions were added to provide a reproducible environment.

## Architectural deviations

- Initial design assumed a separate microservice for e‑mail polling. In the final version the polling logic is
  embedded in the main Flask application for simplicity.
- The UI was originally planned in Next.js but was implemented in Streamlit with `streamlit-shadcn-ui` for
  faster prototyping.
- Groq LLM support was added alongside OpenAI/Gemini although not part of the original plan.
- Demo mode with sample data and HTML emails allows testing the dashboard without real accounts.
- A Service Impact Dashboard lets users edit or delete notifications and view affected systems.
- Downtime events are tracked per service and statistics can be queried via the API.
- An endpoint to update email configuration was added for easier deployment.
- HTML email parsing was implemented for more realistic provider messages.

## Build & run guide

1. **Install locally**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # adjust credentials
   python main.py
   ```
2. **Run tests**
   ```bash
   pytest
   ```
3. **Docker Compose**
   Ensure a copy of `.env` exists (see `.env.example` lines 1‑34 for the required values).
   Then launch all services:
   ```bash
   docker compose up --build
   ```
   The API listens on port 5001 and the dashboard on 8501 as defined in
   `docker-compose.yml` lines 13–33.

Dockerfile lines 1–35 show how the container is built and starts `main.py`.

## Task allocation

Development was primarily carried out by **theemperor66**, with contributions from **Zaid Marzguioui**. All
modules under `src/` were co-developed, while the Streamlit UI in `scripts/` was mainly implemented by
`theemperor66`.

## Further material

- `.env.example` documents all environment variables including e‑mail credentials and LLM keys
  (lines 1–34).
- API endpoints are provided by `main.py`; for instance the health check at `/api/v1/health` and CRUD routes
  for services, systems and notifications.
- Unit tests under `tests/` illustrate usage, e.g. the impact analysis test
  (`tests/unit/analysis/test_impact_analysis.py` lines 1‑34).
- Demo HTML e‑mails in `scripts/demo_emails` can be processed via the dashboard.
- Future improvements include better authentication, background job scheduling and advanced notification
  templates.
