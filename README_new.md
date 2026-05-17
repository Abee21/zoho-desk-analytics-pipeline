# Zoho Desk Analytics Pipeline

> A end-to-end data engineering project — automated ticket analytics pipeline with dual-view dashboards, built using Python, Google Sheets, n8n, and Looker Studio.

---

## Project Overview

This pipeline solves a real business problem in support operations: **managers see ticket counts, but agents work on thread interactions**. A ticket reopened 4 times looks like 1 ticket to a manager — but represents 4× the actual work for the agent.

This system makes both views visible simultaneously, automates all data collection and analysis, and serves role-specific dashboards to different teams — at zero additional cost.

---

## Architecture

```
Zoho Desk (source)
      ↓  REST API — daily at midnight
n8n (automation engine)
      ↓  Google Sheets API
Google Sheets — raw_tickets (live 12 months)
      ↓                    ↘
Python Analysis         Google Drive Archive
(zoho_data_manager.py)  (Parquet files > 12 months)
      ↓
15 KPI tabs in Google Sheets
      ↓  auto-refresh every 12 hours
Looker Studio (free)
      ↓
Role-specific dashboards (view-only per team)
```

---

## Key Features

### Dual View System
Every metric is calculated two ways simultaneously:
- **Manager view** — unique tickets (what managers count)
- **Agent view** — total thread interactions (real workload)

This surfaces hidden work from reopened tickets and enables fair performance assessment.

### Correct TAT Definition
TAT (Turnaround Time) = Time from ticket creation → first agent response

Calculated in two ways:
- **Calendar TAT** — raw clock time (includes nights, weekends)
- **Business hours TAT** — fair metric, excludes nights and leave days

### Auto-archiving
n8n automatically moves data older than 12 months from Google Sheets to Google Drive as compressed Parquet files (60-80% smaller than CSV), preventing Sheets quota limits while preserving full history.

### Role-Based Dashboard Access
One Looker Studio report with 5 pages. Each team receives a view-only URL for their page only — no editing, no cross-team visibility.

---

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Data source | Zoho Desk API | Ticket events, status changes, durations |
| Automation | n8n | Daily sync, archiving trigger |
| Live storage | Google Sheets | Last 12 months of raw data + 15 KPI tabs |
| Cold storage | Google Drive + Parquet | Historical data > 12 months |
| Analysis | Python (pandas, pyarrow) | KPI calculations, dual view, TAT |
| Dashboard | Looker Studio (free) | Multi-page, role-specific dashboards |
| Auth | Google Service Account | Secure API access without passwords |

---

## Repository Structure

```
zoho_pipeline/
│
├── zoho_data_manager.py      # Main analysis engine — reads Sheets, calculates 15 KPI tables
├── load_csv_to_sheets.py     # One-time loader — pushes Zoho CSV export to Google Sheets
├── fix_data_types.py         # Converts text numbers to real numbers for Looker Studio
├── n8n_zoho_sync_workflow.json  # n8n workflow — daily Zoho fetch + archive automation
│
├── archive/                  # Local Parquet archive (gitignored)
├── README.md                 # This file
├── requirements.txt          # Python dependencies
└── .gitignore                # Excludes credentials and data files
```

---

## KPI Tabs Generated

The Python script generates 15 KPI tabs in Google Sheets:

| Tab | Description |
|-----|-------------|
| `kpi_summary` | Single-row headline KPIs for Looker scorecards |
| `kpi_dual_daily` | Manager vs agent view per day |
| `kpi_dual_dow` | Day of week pattern — Mon to Sun |
| `kpi_dual_hourly` | Hour by hour traffic (0–23) |
| `kpi_dual_weekly` | Week by week volume trend |
| `kpi_dual_monthly` | Monthly trend overview |
| `kpi_tat_summary` | TAT headline numbers + response speed buckets |
| `kpi_tat_per_ticket` | TAT for every ticket (calendar + business hours) |
| `kpi_tat_by_dow` | TAT by day of week — shows leave day impact |
| `kpi_tat_by_hour` | TAT by hour — fastest/slowest response windows |
| `kpi_tat_daily` | Daily TAT trend |
| `kpi_ticket_detail` | Full ticket list with TAT, threads, reopen category |
| `kpi_agent_dual` | Agent performance — tickets vs threads vs time |
| `kpi_reopen_distribution` | 1x / 2x / 3x / 4x+ ticket breakdown |
| `kpi_status_flow` | Status transition counts |

---

## Metrics & Definitions

| Metric | Definition | Why It Matters |
|--------|-----------|----------------|
| Unique Tickets | COUNT DISTINCT ticket_id | Manager view — total issues raised |
| Total Threads | COUNT all event rows | Agent view — real interactions worked |
| Thread Multiplier | Total threads ÷ Unique tickets | Quantifies hidden reopen work |
| TAT (Business hrs) | Duration of first event per ticket in business hours | Fair response time — excludes nights and leave |
| TAT (Calendar hrs) | Duration of first event per ticket in clock time | Raw response time |
| Reopen Rate % | Reopen events ÷ New events × 100 | First contact resolution quality |
| FCR Rate % | Tickets opened once ÷ Total × 100 | % resolved without any reopen |
| Responded within 1hr % | Tickets with business TAT ≤ 60 mins ÷ Total × 100 | SLA indicator |
| Tickets Needing Rework | Total tickets − Tickets resolved first try | Management-friendly reopen count |

---

## Dashboard Pages

| Page | Audience | Key Charts |
|------|----------|-----------|
| Executive Summary | Leadership | 6 scorecards, daily dual view, day of week, agent table |
| Time & Peak Analysis | Operations | Hourly heatmap, TAT by day of week, backlog trend |
| Ticket Deep Dive | Support team | Full ticket table, TAT distribution, reopen breakdown |
| Agent Performance | Team leads | Dual view table, closure rate, time per thread |
| Monthly & Status Flow | Analytics | Monthly trend, status transitions, quality over time |

---

## Setup Instructions

### Prerequisites
- Python 3.8+
- Google account (personal or org)
- n8n instance
- Zoho Desk account with API access
- Looker Studio account (free)

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/zoho-desk-analytics.git
cd zoho-desk-analytics

# 2. Create virtual environment
python -m venv zoho_env
source zoho_env/bin/activate  # Windows: zoho_env\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your service_account.json (from Google Cloud)
# See full setup guide in SETUP.md

# 5. Load your Zoho export
python load_csv_to_sheets.py --csv "your_zoho_export.csv"

# 6. Run analysis
python zoho_data_manager.py --action export

# 7. Fix data types for Looker
python fix_data_types.py
```

See `SETUP.md` for the complete step-by-step guide including Google Cloud setup, n8n workflow import, and Looker Studio configuration.

---

## Daily Automation

After setup, the pipeline runs automatically:

| Time | Action | Tool |
|------|--------|------|
| 12:00 AM | Fetch yesterday's Zoho tickets via API | n8n |
| 12:03 AM | Write to Google Sheets raw_tickets | n8n |
| 12:05 AM | Archive rows > 12 months to Drive as Parquet | n8n |
| 12:10 AM | Run KPI analysis, update 15 tabs | Python (scheduled) |
| 12:15 AM | Looker Studio auto-refreshes | Looker |
| Morning | Teams see fresh data on their dashboard | Users |

---

## What I Learned / Built

- Designed a multi-layer storage architecture (Sheets → Parquet → Drive) with automatic archiving
- Built a dual-view analytics system separating manager metrics from agent workload metrics
- Implemented correct TAT calculation using both calendar and business hours
- Created role-based dashboard access using Looker Studio view-only page links
- Automated the full pipeline using n8n with Zoho OAuth2 and Google Sheets API
- Used pandas for complex groupby aggregations, time-series analysis, and data type handling
- Managed Google Sheets as a data warehouse with structured KPI tabs as separate "tables"

---

## Cost

| Tool | Cost |
|------|------|
| Zoho Desk | Existing plan |
| n8n | Existing plan |
| Google Sheets | Free |
| Google Drive | Free (15GB) |
| Python | Free |
| Looker Studio | Free |
| **Total extra cost** | **₹0** |

---

## Author

Built as a proof-of-concept data engineering portfolio project demonstrating:
- API integration and data pipeline design
- ETL (Extract, Transform, Load) with Python and pandas
- Storage architecture and data archiving strategy
- Business intelligence and dashboard design
- Automation and scheduling

---

## License

MIT License — feel free to adapt for your own support analytics use case.
