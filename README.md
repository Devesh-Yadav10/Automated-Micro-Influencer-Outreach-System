# Automated Micro-Influencer Outreach System

**EDXSO AI Engineer Intern Assignment 1**

A modular, production-grade Python system engineered to discover authentic micro-influencers, evaluate and classify them based on niche requirements, record transparent pass/fail auditing trails, generate personalized email pitches and Instagram DMs using LLMs with strict length guardrails, and manage email outreach with simulation and deduplication safeguards.

---

## System Overview & Architecture

The application is structured into decoupled, single-responsibility modules following clean architecture principles:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI & CLI Entry                        │
│                 (Discovery, Audit, Review, Outreach)                   │
└───────────────┬────────────────────────────────────────┬───────────────┘
                │                                        │
┌───────────────▼────────────────┐      ┌────────────────▼───────────────┐
│        Discovery Layer         │      │      Filtering Engine          │
│ - YouTube Data API v3 Client   │      │ - Micro-tier Range Evaluator   │
│ - Verified Real Seed Dataset   │      │ - Niche Relevance Verifier     │
│ - Fictional Data Safeguard     │      │ - Engagement Rate Threshold    │
│ - Pydantic Schema Validation   │      │ - Pass/Fail Justification Log  │
└───────────────┬────────────────┘      └────────────────┬───────────────┘
                │                                        │
┌───────────────▼────────────────┐      ┌────────────────▼───────────────┐
│       Enrichment Layer         │      │     Personalization Engine     │
│ - Bio & Description Parser     │      │ - Gemini / OpenAI LLM Client   │
│ - Public Email Regex Extractor │      │ - Deterministic Fallback Engine│
│ - "Not Found" Normalization    │      │ - Email: 60–90 words strict    │
│ - Content Theme Taxonomy       │      │ - Instagram DM: 15–30 words    │
└───────────────┬────────────────┘      └────────────────┬───────────────┘
                │                                        │
┌───────────────▼────────────────────────────────────────▼───────────────┐
│                      Outreach & Persistence Layer                      │
│ - Deduplication Guard (Prevents repeated channel outreach)             │
│ - Safe Simulation Dispatcher (Default: zero network traffic)           │
│ - Optional Guarded SMTP Delivery (Requires explicit confirmation)      │
│ - Manual/Simulated Instagram DM Workflow                               │
│ - SQLite Database (Influencers, Audits, Messages, Outreach Logs)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features & Implementations

### 1. Data Discovery & Enrichment (Phase 2)
- **Official YouTube Data API v3 Connector** (`src/discovery/youtube_source.py`):
  - Ingests public metadata, subscriber tiers, and uploads playlist items.
  - **Recent-Video Engagement Rate Proxy**:
    $$\text{Engagement Rate} = \frac{\sum (\text{likes} + \text{comments})}{\sum \text{views}} \times 100$$
    *Observation window*: Up to 5 most recent public uploads.
    *Limitation*: Represents a recent video proxy; not a lifetime or cross-platform engagement metric.
- **Genuine 52-Creator Seed Dataset** (`data/verified_tech_influencers.json`):
  - 52 real, public YouTube creators in Technology / AI / Machine Learning.
  - No synthetic records or fabricated metrics.
- **Data Quality & Enrichment** (`src/enrichment/extractor.py`):
  - Extracts business emails exclusively from public bios/descriptions.
  - Rejects false positives (asset files like `.png`, placeholder domains like `@example.com`).
  - Genuinely unavailable emails normalize strictly to `"Not Found"`. Never guesses or invents emails.

### 2. Filtering & Classification (Phase 3)
- **Modular Rule Set** (`src/filtering/rules.py`):
  - `MicroInfluencerTierRule`: Enforces 5,000–100,000 subscriber micro-tier.
  - `NicheRelevanceRule`: Evaluates content themes and descriptions against Technology / AI taxonomy.
  - `EngagementRateRule`: Configurable minimum threshold (e.g. $\ge 2.0\%$). Unknown metrics trigger `NEEDS_REVIEW` rather than failing as zero.
  - `DataQualityRule`: Validates URL schemas and provenance timestamps. Missing emails are marked as `email_outreach_ready: False` without disqualifying candidates from discovery or DM outreach.
- **Transparent Decisions**:
  - `QUALIFIED`: Satisfies all criteria.
  - `DISQUALIFIED`: Hard failure (e.g. >100k macro-tier).
  - `NEEDS_REVIEW`: Insufficient evidence or unknown required metrics.
  - Audit logs saved to SQLite table `filtering_audits` preserving historical runs.

### 3. Personalization Engine (Phase 4)
- **Strict Word-Count Guardrails** (`src/personalization/validator.py`):
  - **Email Collaboration Pitch**: **60–90 words** strictly. Includes subject line and collaboration value proposition.
  - **Instagram DM**: **15–30 words** strictly. Natural, concise, and references verified content themes.
- **LLM Integration & Deterministic Fallback** (`src/personalization/llm_client.py` & `src/personalization/fallback.py`):
  - Supports Google Gemini and OpenAI when configured in `.env`.
  - **Zero-Dependency Guarantee**: If API keys are omitted or external calls fail, the engine automatically switches to a deterministic template generator that mathematically guarantees adherence to word-count boundaries (60–90 words for emails, 15–30 words for DMs) and references real profile themes.

### 4. Outreach Simulation & Deduplication (Phase 5)
- **Default Safe Simulation** (`src/outreach/email_service.py`):
  - Generates zero network calls in simulation mode. Logs dispatch status as `SIMULATED_SENT` with UTC timestamps.
  - Creators with email `"Not Found"` are automatically blocked from email dispatch.
- **Multi-Level Deduplication Policy** (`src/storage/database.py`):
  - Creators can only be contacted once per channel (e.g. `(influencer_id, 'email')`). Subsequent outreach attempts are rejected as duplicates.
- **Manual Instagram DM Workflow** (`src/outreach/dispatcher.py`):
  - Does not implement unauthorized automated scraping or bot sending.
  - Displays generated DMs for operator review and records dispatches as `MANUAL_SENT` or `SIMULATED_SENT`.

### 5. Streamlit Demonstration Dashboard (Phase 6)
- **Interactive Multi-Section App** (`app.py`):
  - **Overview**: System KPI cards, audience distribution charts, classification metrics.
  - **Influencer Explorer**: Full search, multi-factor filtering, deep-dive profile inspector.
  - **Filtering & Audit**: Interactive parameter adjustments and one-click CSV audit trail download.
  - **Personalized Pitches**: Side-by-side pitch generation, live word counter with validation badges.
  - **Outreach Tracker**: Single and batch simulated dispatches, manual DM recording, live activity logs.
  - **Import & Export**: Upload external CSV/JSON files, download complete database tables.
  - **Safety Policy**: Opening or refreshing the page **never** triggers outreach or mutates data.

---

## Installation & Setup

### Prerequisites
- Python **3.11+** (Tested on Python 3.15.0)
- Windows PowerShell or Unix Shell

### 1. Virtual Environment Setup
```powershell
# Windows PowerShell
.\myenv\Scripts\Activate.ps1
```
Or create a fresh environment:
```powershell
python -m venv myenv
.\myenv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the template configuration:
```powershell
cp .env.example .env
```
Default parameters in `.env`:
```ini
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_PATH=data/micro_influencer.db
OUTREACH_MODE=simulation
LLM_PROVIDER=fallback
YOUTUBE_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
```

---

## Execution Guide

### 1. Launch the Demonstration Dashboard
```powershell
streamlit run app.py
```
*Access the local web dashboard at `http://localhost:8501`.*

### 2. Command-Line Workflows (`main.py`)

#### A. Initialize Database & View Status
```powershell
python main.py --init-db --status
```

#### B. Ingest Verified Influencer Dataset
```powershell
python main.py --import-seed
```

#### C. Run Filtering & Export Audit CSV
```powershell
python main.py --filter --export-csv data/audit_report.csv
```

#### D. Generate Personalized Pitches (60–90w Email, 15–30w DM)
```powershell
python main.py --generate-messages
```

#### E. Execute Safe Simulated Outreach Batch
```powershell
python main.py --simulate-outreach
```

---

## Verified Dataset Audit Summary

Audit of the 52 real Technology / AI creator records in `data/verified_tech_influencers.json`:

| Metric | Count | Percentage | Operational Impact |
| :--- | :--- | :--- | :--- |
| **Total Discovered Records** | **52** | 100% | Verified YouTube channels in Technology / AI / ML. |
| **Micro-Tier (5,000–100,000)** | **45** | **86.5%** | **QUALIFIED** for personalized outreach. |
| **Macro-Tier (> 100,000)** | **7** | **13.5%** | **DISQUALIFIED** (e.g. Sentdex, Krish Naik, Yannic Kilcher). |
| **Below Minimum (< 5,000)** | **0** | 0.0% | None below 5,000 subscribers. |
| **Public Email Verified** | **39** | **75.0%** | Ready for simulated email outreach. |
| **Contact Email "Not Found"** | **13** | **25.0%** | Retained on shortlist for Instagram DM outreach. |
| **Generated Pitches** | **45** | 100% | All qualified creators have 60–90w emails & 15–30w DMs. |

---

## Automated Test Suite

Run the full pytest suite covering data models, SQLite storage, YouTube discovery, regex enrichment, filtering rules, word-count boundaries, LLM fallbacks, simulation dispatch, and deduplication:

```powershell
python -m pytest tests/ -v
```

All **56 unit tests** execute against temporary, isolated SQLite databases with mocked network calls. No API credentials or live Internet connections are required to run tests.
