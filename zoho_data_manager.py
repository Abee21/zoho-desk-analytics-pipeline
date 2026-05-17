"""
zoho_data_manager.py — Complete Final Version
==============================================
All metrics included:
  - Dual view (manager: unique tickets | agent: total threads)
  - Correct TAT = ticket created → first agent response (duration of first event)
  - Business hours TAT (fair — excludes nights, weekends, leave)
  - Calendar TAT (raw clock time)
  - First response time
  - Reopen analysis
  - Agent dual view
  - Day of week TAT (shows if leave days affect resolution)
  - Hourly patterns
  - Weekly / monthly trends

Usage:
    python zoho_data_manager.py --action export
    python zoho_data_manager.py --action analyze
    python zoho_data_manager.py --action load
"""

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import argparse

# ── Configuration ──────────────────────────────────────────────────────────────
CONFIG = {
    "service_account_json": "service_account.json",
    "google_sheet_id":      "1jfeqntRgPpQmY49r9YaRlgTzXI5vP9QsUuW-BXj131Y",
    "sheet_tab_name":       "raw_tickets",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Google Sheets helpers ──────────────────────────────────────────────────────
def get_client():
    creds = Credentials.from_service_account_file(
        CONFIG["service_account_json"], scopes=SCOPES
    )
    return gspread.authorize(creds)


def load_from_sheets():
    print("📊 Loading data from Google Sheets...")
    gc     = get_client()
    sh     = gc.open_by_key(CONFIG["google_sheet_id"])
    ws     = sh.worksheet(CONFIG["sheet_tab_name"])
    df     = pd.DataFrame(ws.get_all_records())

    if df.empty:
        print("   ⚠️  Sheet is empty!")
        return df

    # Parse date/time columns
    for col in ['event_start', 'event_end', 'created_date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Parse numeric columns
    for col in ['duration_minutes', 'duration_biz_minutes', 'created_hour']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    print(f"   ✅ Loaded {len(df):,} rows — {df['ticket_id'].nunique()} unique tickets")
    return df


def write_tab(tab_name, df):
    print(f"   Writing '{tab_name}'...", end=' ')
    gc = get_client()
    sh = gc.open_by_key(CONFIG["google_sheet_id"])
    try:
        ws = sh.worksheet(tab_name)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=tab_name,
            rows=str(len(df) + 10),
            cols=str(len(df.columns) + 2)
        )
    out = df.fillna('').astype(str)
    ws.update([out.columns.tolist()] + out.values.tolist())
    print(f"✅ {len(df)} rows")


# ── Main analysis ──────────────────────────────────────────────────────────────
def run_all(df):
    results = {}

    # ── Classify every row by event type ──────────────────────────────────────
    df = df.copy()
    df['event_type'] = 'other'
    df.loc[df['status_from'] == '-',                                          'event_type'] = 'new'
    df.loc[(df['status_from'] == 'Closed') & (df['status_to'] == 'Open'),    'event_type'] = 'reopen'
    df.loc[df['status_to'] == 'Closed',                                       'event_type'] = 'closure'

    df['event_date']  = df['event_start'].dt.strftime('%Y-%m-%d')
    df['day_of_week'] = df['event_start'].dt.day_name()
    df['hour']        = df['event_start'].dt.hour
    df['month']       = df['event_start'].dt.strftime('%Y-%m')
    df['week']        = df['event_start'].dt.isocalendar().week.astype(str)

    new_df     = df[df['event_type'] == 'new']
    reopen_df  = df[df['event_type'] == 'reopen']
    closure_df = df[df['event_type'] == 'closure']

    # ── 1. CORRECT TAT ────────────────────────────────────────────────────────
    # TAT = ticket created → first agent response
    # = duration_minutes of the FIRST event row per ticket (where status_from = '-')
    # This is the correct definition: how long from ticket creation to first touch
    tat_df = new_df[['ticket_id', 'duration_minutes', 'duration_biz_minutes',
                     'event_date', 'day_of_week', 'hour', 'month', 'week']].copy()
    tat_df = tat_df.rename(columns={
        'duration_minutes':     'tat_calendar_mins',
        'duration_biz_minutes': 'tat_business_mins',
    })
    tat_df['tat_calendar_hrs'] = (tat_df['tat_calendar_mins'] / 60).round(2)
    tat_df['tat_business_hrs'] = (tat_df['tat_business_mins'] / 60).round(2)

    # TAT category buckets
    def tat_bucket(hrs):
        if pd.isna(hrs):      return 'Unknown'
        if hrs <= 1:          return 'Within 1 hr'
        if hrs <= 4:          return 'Within 4 hrs'
        if hrs <= 8:          return 'Within 8 hrs (same day)'
        if hrs <= 24:         return 'Within 24 hrs'
        if hrs <= 72:         return 'Within 3 days'
        return                       'Over 3 days'

    tat_df['tat_bucket_calendar'] = tat_df['tat_calendar_hrs'].apply(tat_bucket)
    tat_df['tat_bucket_business'] = tat_df['tat_business_hrs'].apply(tat_bucket)
    results['kpi_tat_per_ticket'] = tat_df
    print("   ✅ kpi_tat_per_ticket (correct TAT = created → first response)")

    # ── 2. TAT SUMMARY ────────────────────────────────────────────────────────
    # Both calendar and business hours side by side
    total_tix = len(tat_df)
    results['kpi_tat_summary'] = pd.DataFrame([{
        # Calendar TAT (includes nights, weekends, leave)
        'avg_tat_calendar_hrs':       round(tat_df['tat_calendar_hrs'].mean(), 2),
        'median_tat_calendar_hrs':    round(tat_df['tat_calendar_hrs'].median(), 2),
        'min_tat_calendar_mins':      round(tat_df['tat_calendar_mins'].min(), 0),
        'max_tat_calendar_hrs':       round(tat_df['tat_calendar_hrs'].max(), 2),
        # Business hours TAT (fair — excludes nights, weekends, leave days)
        'avg_tat_business_hrs':       round(tat_df['tat_business_hrs'].mean(), 2),
        'median_tat_business_hrs':    round(tat_df['tat_business_hrs'].median(), 2),
        'min_tat_business_mins':      round(tat_df['tat_business_mins'].min(), 0),
        'max_tat_business_hrs':       round(tat_df['tat_business_hrs'].max(), 2),
        # Response speed buckets (business hours)
        'within_1hr_count':           int((tat_df['tat_business_hrs'] <= 1).sum()),
        'within_1hr_pct':             round((tat_df['tat_business_hrs'] <= 1).sum() / total_tix * 100, 2),
        'within_4hr_count':           int((tat_df['tat_business_hrs'] <= 4).sum()),
        'within_4hr_pct':             round((tat_df['tat_business_hrs'] <= 4).sum() / total_tix * 100, 2),
        'within_24hr_count':          int((tat_df['tat_business_hrs'] <= 24).sum()),
        'within_24hr_pct':            round((tat_df['tat_business_hrs'] <= 24).sum() / total_tix * 100, 2),
        'over_24hr_count':            int((tat_df['tat_business_hrs'] > 24).sum()),
        'over_24hr_pct':              round((tat_df['tat_business_hrs'] > 24).sum() / total_tix * 100, 2),
        'total_tickets':              total_tix,
        'report_date':                datetime.now().strftime('%Y-%m-%d'),
    }])
    print("   ✅ kpi_tat_summary")

    # ── 3. TAT BY DAY OF WEEK ─────────────────────────────────────────────────
    # Shows if Monday/Friday (leave days) have worse TAT than other days
    dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    tat_dow = tat_df.groupby('day_of_week').agg(
        ticket_count          =('ticket_id', 'count'),
        avg_tat_calendar_hrs  =('tat_calendar_hrs', 'mean'),
        median_tat_calendar_hrs=('tat_calendar_hrs','median'),
        avg_tat_business_hrs  =('tat_business_hrs', 'mean'),
        median_tat_business_hrs=('tat_business_hrs','median'),
    ).reindex(dow_order).fillna(0).reset_index().round(2)
    results['kpi_tat_by_dow'] = tat_dow
    print("   ✅ kpi_tat_by_dow (shows leave day impact on response time)")

    # ── 4. TAT BY HOUR ────────────────────────────────────────────────────────
    # Shows which hours of day have fastest first response
    tat_hour = tat_df.groupby('hour').agg(
        ticket_count           =('ticket_id', 'count'),
        avg_tat_business_hrs   =('tat_business_hrs', 'mean'),
        median_tat_business_hrs=('tat_business_hrs', 'median'),
    ).reset_index().round(2)
    results['kpi_tat_by_hour'] = tat_hour
    print("   ✅ kpi_tat_by_hour")

    # ── 5. TAT DAILY TREND ────────────────────────────────────────────────────
    tat_daily = tat_df.groupby('event_date').agg(
        tickets_received       =('ticket_id', 'count'),
        avg_tat_business_hrs   =('tat_business_hrs', 'mean'),
        median_tat_business_hrs=('tat_business_hrs', 'median'),
        avg_tat_calendar_hrs   =('tat_calendar_hrs', 'mean'),
    ).reset_index().round(2)
    results['kpi_tat_daily'] = tat_daily
    print("   ✅ kpi_tat_daily")

    # ── 6. DUAL VIEW — DAILY ──────────────────────────────────────────────────
    # Manager view (unique tickets) vs Agent view (total threads) per day
    mgr_daily   = new_df.groupby('event_date')['ticket_id'].nunique().rename('unique_tickets')
    agt_daily   = df.groupby('event_date')['ticket_id'].count().rename('total_threads')
    close_daily = closure_df.groupby('event_date')['ticket_id'].count().rename('closures')
    reopen_daily= reopen_df.groupby('event_date')['ticket_id'].count().rename('reopens')

    daily = pd.concat([mgr_daily, agt_daily, close_daily, reopen_daily], axis=1).fillna(0).reset_index()
    daily['net_pending']    = daily['unique_tickets'] - daily['closures']
    daily['thread_ratio']   = (daily['total_threads'] / daily['unique_tickets'].replace(0, 1)).round(2)
    daily = daily.sort_values('event_date')
    results['kpi_dual_daily'] = daily
    print("   ✅ kpi_dual_daily")

    # ── 7. DUAL VIEW — DAY OF WEEK ────────────────────────────────────────────
    dow_mgr = new_df.groupby('day_of_week')['ticket_id'].nunique().rename('unique_tickets')
    dow_agt = df.groupby('day_of_week')['ticket_id'].count().rename('total_threads')
    dow_cls = closure_df.groupby('day_of_week')['ticket_id'].count().rename('closures')
    dow = pd.concat([dow_mgr, dow_agt, dow_cls], axis=1).reindex(dow_order).fillna(0).reset_index()
    dow['thread_ratio'] = (dow['total_threads'] / dow['unique_tickets'].replace(0,1)).round(2)
    results['kpi_dual_dow'] = dow
    print("   ✅ kpi_dual_dow")

    # ── 8. DUAL VIEW — HOURLY ─────────────────────────────────────────────────
    hr_mgr = new_df.groupby('hour')['ticket_id'].nunique().rename('unique_tickets')
    hr_agt = df.groupby('hour')['ticket_id'].count().rename('total_threads')
    hourly = pd.concat([hr_mgr, hr_agt], axis=1).fillna(0).reset_index()
    hourly['thread_ratio'] = (hourly['total_threads'] / hourly['unique_tickets'].replace(0,1)).round(2)
    results['kpi_dual_hourly'] = hourly
    print("   ✅ kpi_dual_hourly")

    # ── 9. DUAL VIEW — WEEKLY ─────────────────────────────────────────────────
    wk_mgr = new_df.groupby('week')['ticket_id'].nunique().rename('unique_tickets')
    wk_agt = df.groupby('week')['ticket_id'].count().rename('total_threads')
    weekly = pd.concat([wk_mgr, wk_agt], axis=1).fillna(0).reset_index()
    weekly['thread_ratio'] = (weekly['total_threads'] / weekly['unique_tickets'].replace(0,1)).round(2)
    results['kpi_dual_weekly'] = weekly
    print("   ✅ kpi_dual_weekly")

    # ── 10. DUAL VIEW — MONTHLY ───────────────────────────────────────────────
    mo_mgr = new_df.groupby('month')['ticket_id'].nunique().rename('unique_tickets')
    mo_agt = df.groupby('month')['ticket_id'].count().rename('total_threads')
    monthly = pd.concat([mo_mgr, mo_agt], axis=1).fillna(0).reset_index()
    monthly['thread_ratio'] = (monthly['total_threads'] / monthly['unique_tickets'].replace(0,1)).round(2)
    results['kpi_dual_monthly'] = monthly
    print("   ✅ kpi_dual_monthly")

    # ── 11. PER-TICKET DETAIL ─────────────────────────────────────────────────
    ticket_detail = df.groupby('ticket_id').agg(
        first_event   =('event_start', 'min'),
        last_event    =('event_start', 'max'),
        thread_count  =('ticket_id', 'count'),
        times_opened  =('status_to', lambda x: (x == 'Open').sum()),
        times_closed  =('status_to', lambda x: (x == 'Closed').sum()),
        ever_reopened =('status_from', lambda x: 'Closed' in x.values),
        modified_by   =('modified_by', lambda x: x.dropna().iloc[0] if len(x.dropna()) > 0 else ''),
    ).reset_index()

    ticket_detail['full_lifecycle_hrs'] = (
        (ticket_detail['last_event'] - ticket_detail['first_event'])
        .dt.total_seconds() / 3600
    ).round(2)
    ticket_detail['day_of_week']  = ticket_detail['first_event'].dt.day_name()
    ticket_detail['month']        = ticket_detail['first_event'].dt.strftime('%Y-%m')
    ticket_detail['open_category'] = ticket_detail['times_opened'].apply(
        lambda x: '1x - resolved first try' if x == 1
        else '2x - one reopen' if x == 2
        else '3x - two reopens' if x == 3
        else '4x+ - chronic'
    )
    ticket_detail['ever_reopened'] = ticket_detail['ever_reopened'].astype(str)
    ticket_detail['first_event']   = ticket_detail['first_event'].dt.strftime('%Y-%m-%d %H:%M')
    ticket_detail['last_event']    = ticket_detail['last_event'].dt.strftime('%Y-%m-%d %H:%M')

    # Merge TAT (first response time) into ticket detail
    ticket_detail = ticket_detail.merge(
        tat_df[['ticket_id','tat_calendar_hrs','tat_business_hrs','tat_bucket_business']],
        on='ticket_id', how='left'
    )
    results['kpi_ticket_detail'] = ticket_detail
    print("   ✅ kpi_ticket_detail (includes TAT per ticket)")

    # ── 12. REOPEN DISTRIBUTION ───────────────────────────────────────────────
    reopen_dist = ticket_detail.groupby('open_category').agg(
        ticket_count=('ticket_id', 'count')
    ).reset_index()
    results['kpi_reopen_distribution'] = reopen_dist
    print("   ✅ kpi_reopen_distribution")

    # ── 13. AGENT DUAL VIEW ───────────────────────────────────────────────────
    agent = df[df['modified_by'].str.strip() != ''].groupby('modified_by').agg(
        unique_tickets  =('ticket_id', 'nunique'),
        total_threads   =('ticket_id', 'count'),
        tickets_closed  =('status_to', lambda x: (x == 'Closed').sum()),
        tickets_opened  =('status_to', lambda x: (x == 'Open').sum()),
        total_time_mins =('duration_minutes', 'sum'),
    ).reset_index()
    agent['threads_per_ticket']  = (agent['total_threads']   / agent['unique_tickets']).round(2)
    agent['avg_mins_per_thread'] = (agent['total_time_mins'] / agent['total_threads']).round(1)
    agent['avg_mins_per_ticket'] = (agent['total_time_mins'] / agent['unique_tickets']).round(1)
    agent['closure_rate_pct']    = (agent['tickets_closed']  / agent['total_threads'] * 100).round(1)
    results['kpi_agent_dual'] = agent
    print("   ✅ kpi_agent_dual")

    # ── 14. STATUS FLOW ───────────────────────────────────────────────────────
    status_flow = df.groupby(['status_from','status_to']).size().reset_index(name='count')
    results['kpi_status_flow'] = status_flow
    print("   ✅ kpi_status_flow")

    # ── 15. OVERALL SUMMARY — single row for Looker scorecards ───────────────
    total_unique   = df['ticket_id'].nunique()
    new_events     = len(new_df)
    reopen_events  = len(reopen_df)
    close_events   = len(closure_df)
    total_threads  = len(df)
    once           = (ticket_detail['times_opened'] == 1).sum()
    twice          = (ticket_detail['times_opened'] == 2).sum()
    three_plus     = (ticket_detail['times_opened'] >= 3).sum()
    closed_tix     = ticket_detail[ticket_detail['times_closed'] > 0]

    results['kpi_summary'] = pd.DataFrame([{
        'report_date':                  datetime.now().strftime('%Y-%m-%d'),
        # Volume
        'unique_tickets':               int(total_unique),
        'total_threads':                int(total_threads),
        'new_ticket_events':            int(new_events),
        'reopen_events':                int(reopen_events),
        'closure_events':               int(close_events),
        # TAT — correct definition (created → first response)
        'avg_tat_calendar_hrs':         round(tat_df['tat_calendar_hrs'].mean(), 2),
        'median_tat_calendar_hrs':      round(tat_df['tat_calendar_hrs'].median(), 2),
        'avg_tat_business_hrs':         round(tat_df['tat_business_hrs'].mean(), 2),
        'median_tat_business_hrs':      round(tat_df['tat_business_hrs'].median(), 2),
        # Response speed
        'responded_within_1hr_pct':     round((tat_df['tat_business_hrs'] <= 1).sum() / total_unique * 100, 2),
        'responded_within_4hr_pct':     round((tat_df['tat_business_hrs'] <= 4).sum() / total_unique * 100, 2),
        'responded_within_24hr_pct':    round((tat_df['tat_business_hrs'] <= 24).sum() / total_unique * 100, 2),
        # Quality
        'closure_rate_pct':             round(len(closed_tix) / total_unique * 100, 2),
        'reopen_rate_pct':              round(reopen_events / new_events * 100, 2),
        'hidden_work_pct':              round(reopen_events / total_threads * 100, 2),
        'first_contact_resolution_pct': round(int(once) / total_unique * 100, 2),
        'tickets_resolved_first_try':   int(once),
        'tickets_opened_2x':            int(twice),
        'tickets_opened_3x_plus':       int(three_plus),
        'tickets_needing_rework':       int(total_unique - once),
    }])
    print("   ✅ kpi_summary (all scorecards + correct TAT)")

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Zoho Desk Analytics — Complete Version")
    parser.add_argument('--action', choices=['load', 'analyze', 'export'], required=True,
        help="load: preview data | analyze: print KPIs | export: push all to Sheets")
    args = parser.parse_args()

    df = load_from_sheets()
    if df.empty:
        return

    if args.action == 'load':
        print(df.head(10).to_string())
        print(f"\nShape: {df.shape}")
        print(f"Unique tickets: {df['ticket_id'].nunique()}")
        print(f"Total threads:  {len(df)}")
        print(f"Date range:     {df['event_start'].min()} → {df['event_start'].max()}")

    elif args.action == 'analyze':
        print("\n🔍 Running analysis...\n")
        results = run_all(df)
        for name, rdf in results.items():
            print(f"\n{'='*55}\n📊 {name.upper()}")
            print(rdf.to_string(index=False))

    elif args.action == 'export':
        print("\n🔍 Running analysis...")
        results = run_all(df)
        print(f"\n📤 Writing {len(results)} KPI tabs to Google Sheets...")
        for name, rdf in results.items():
            write_tab(name, rdf)
        print(f"\n🎉 Done! {len(results)} KPI tabs updated.")
        print(f"   https://docs.google.com/spreadsheets/d/{CONFIG['google_sheet_id']}")


if __name__ == "__main__":
    main()
