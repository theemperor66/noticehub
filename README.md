# NoticeHub

AI-powered analysis and processing of service uptime notifications

## Project Overview

NoticeHub is an intelligent system that processes service uptime notifications from external providers, analyzes them using AI, and generates internal notifications for affected systems.

## Setup Instructions

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Unix/macOS
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example environment file and configure it:
```bash
cp .env.example .env
```

4. Add your API keys and credentials to the `.env` file. Supported LLM providers are **openai**, **google/gemini**, and **groq**.

## Project Structure

```
noticehub/
├── src/              # Source code
│   ├── data/          # Database models and operations
│   ├── email/         # Email processing
│   ├── llm/           # LLM integration
│   ├── notifications/ # Notification helpers
│   └── utils/         # Utilities
├── scripts/          # Helper scripts and Streamlit UI
├── tests/            # Test files
├── .env              # Environment variables
├── .env.example      # Example environment file
├── requirements.txt  # Python dependencies
└── README.md         # Project documentation
```

## Development

The project follows a structured development approach with multiple work packages:

1. WP1: Familiarization, Setup & LLM Basics
2. WP2: Email Integration & Pre-filtering
3. WP3: LLM-based Data Extraction
4. WP4: Database Modeling & Implementation
5. WP5: Dependency Analysis
6. WP6: Notification Generation
7. WP7: System Integration & Workflow Orchestration
8. WP8: Testing, Error Handling & Validation
9. WP9: Project Documentation & Final Report

## Running Tests

Install dependencies and copy the example environment file:

```bash
pip install -r requirements.txt
cp .env.example .env
pytest
```

## Sample Data

The dashboard loads a demo dataset on startup that represents a
fictional company using common cloud providers such as AWS, Azure,
Google Cloud, GitHub and Cloudflare. If the backend API has no data
yet, these examples are shown on their own. Once real notifications are
created they are **merged** with the demo entries so the initial
examples remain visible.

You can also process example HTML emails directly from the
"Notifications" page. Selecting a demo email shows a small preview and
the file can be sent to the backend through `/api/v1/process-html-email`
for full LLM processing. Several sample provider emails are available in
`scripts/demo_emails`.

An API endpoint `/api/v1/email-config` is available for retrieving and
updating email configuration when running against the real backend.
