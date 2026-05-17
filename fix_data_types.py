"""
fix_data_types.py — Complete Final Version
===========================================
Converts all text numbers to real numbers across all KPI tabs
so Looker Studio can use them for charts and calculations.

Run after every export:
    python fix_data_types.py
"""

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

CONFIG = {
    "service_account_json": "service_account.json",
    "google_sheet_id":      "1jfeqntRgPpQmY49r9YaRlgTzXI5vP9QsUuW-BXj131Y",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Which columns should be numbers in each tab ────────────────────────────────
NUMERIC_COLS = {
    "kpi_summary": [
        "unique_tickets", "total_threads", "new_ticket_events",
        "reopen_events", "closure_events",
        "avg_tat_calendar_hrs", "median_tat_calendar_hrs",
        "avg_tat_business_hrs", "median_tat_business_hrs",
        "responded_within_1hr_pct", "responded_within_4hr_pct",
        "responded_within_24hr_pct", "closure_rate_pct",
        "reopen_rate_pct", "hidden_work_pct",
        "first_contact_resolution_pct", "tickets_resolved_first_try",
        "tickets_opened_2x", "tickets_opened_3x_plus",
        "tickets_needing_rework",
    ],
    "kpi_tat_summary": [
        "avg_tat_calendar_hrs", "median_tat_calendar_hrs",
        "min_tat_calendar_mins", "max_tat_calendar_hrs",
        "avg_tat_business_hrs", "median_tat_business_hrs",
        "min_tat_business_mins", "max_tat_business_hrs",
        "within_1hr_count", "within_1hr_pct",
        "within_4hr_count", "within_4hr_pct",
        "within_24hr_count", "within_24hr_pct",
        "over_24hr_count", "over_24hr_pct",
        "total_tickets",
    ],
    "kpi_tat_per_ticket": [
        "ticket_id", "tat_calendar_mins", "tat_business_mins",
        "tat_calendar_hrs", "tat_business_hrs",
    ],
    "kpi_tat_by_dow": [
        "ticket_count",
        "avg_tat_calendar_hrs", "median_tat_calendar_hrs",
        "avg_tat_business_hrs", "median_tat_business_hrs",
    ],
    "kpi_tat_by_hour": [
        "hour", "ticket_count",
        "avg_tat_business_hrs", "median_tat_business_hrs",
    ],
    "kpi_tat_daily": [
        "tickets_received",
        "avg_tat_business_hrs", "median_tat_business_hrs",
        "avg_tat_calendar_hrs",
    ],
    "kpi_dual_daily": [
        "unique_tickets", "total_threads", "closures",
        "reopens", "net_pending", "thread_ratio",
    ],
    "kpi_dual_dow": [
        "unique_tickets", "total_threads", "closures", "thread_ratio",
    ],
    "kpi_dual_hourly": [
        "hour", "unique_tickets", "total_threads", "thread_ratio",
    ],
    "kpi_dual_weekly": [
        "unique_tickets", "total_threads", "thread_ratio",
    ],
    "kpi_dual_monthly": [
        "unique_tickets", "total_threads", "thread_ratio",
    ],
    "kpi_ticket_detail": [
        "ticket_id", "thread_count", "times_opened", "times_closed",
        "full_lifecycle_hrs", "tat_calendar_hrs", "tat_business_hrs",
    ],
    "kpi_agent_dual": [
        "unique_tickets", "total_threads", "tickets_closed",
        "tickets_opened", "total_time_mins", "threads_per_ticket",
        "avg_mins_per_thread", "avg_mins_per_ticket", "closure_rate_pct",
    ],
    "kpi_reopen_distribution": [
        "ticket_count",
    ],
    "kpi_status_flow": [
        "count",
    ],
}


def fix_tab(gc, sh, tab_name, numeric_cols):
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        print(f"   ⚠️  '{tab_name}' not found — skipping")
        return

    data = ws.get_all_records()
    if not data:
        print(f"   ⚠️  '{tab_name}' is empty — skipping")
        return

    df = pd.DataFrame(data)

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    rows = [df.columns.tolist()]
    for _, row in df.iterrows():
        out_row = []
        for val in row:
            if pd.isna(val):
                out_row.append('')
            elif isinstance(val, float) and val == int(val):
                out_row.append(int(val))
            else:
                out_row.append(val)
        rows.append(out_row)

    ws.clear()
    ws.update(rows, value_input_option='USER_ENTERED')
    print(f"   ✅ '{tab_name}' — {len(df)} rows fixed")


def main():
    print("🔗 Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(
        CONFIG["service_account_json"], scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(CONFIG["google_sheet_id"])

    print(f"\n🔧 Fixing data types in {len(NUMERIC_COLS)} KPI tabs...\n")
    for tab_name, numeric_cols in NUMERIC_COLS.items():
        fix_tab(gc, sh, tab_name, numeric_cols)

    print("\n✅ All tabs fixed!")
    print("   Refresh Looker Studio — all fields now show 123 not ABC.")
    print(f"   https://docs.google.com/spreadsheets/d/{CONFIG['google_sheet_id']}")


if __name__ == "__main__":
    main()
