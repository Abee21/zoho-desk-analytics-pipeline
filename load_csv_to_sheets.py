"""
load_csv_to_sheets.py
=====================
One-time script to load your Zoho lifecycle CSV into Google Sheets.
Run this once to populate the raw_tickets tab.

Usage:
    python load_csv_to_sheets.py --csv "ExportReport_1778911430359.csv"
"""

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import argparse
from datetime import datetime

CONFIG = {
    "service_account_json": "service_account.json",
    "google_sheet_id":      "1jfeqntRgPpQmY49r9YaRlgTzXI5vP9QsUuW-BXj131Y",
    "sheet_tab_name":       "raw_tickets",
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def parse_duration_to_minutes(d):
    try:
        parts = str(d).split(':')
        return round(int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60, 2)
    except:
        return None

def load_csv(csv_path):
    print(f"📂 Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path, skiprows=3)

    # Remove the last summary row if present
    df = df[df['TICKET ID'].apply(lambda x: str(x).strip().isdigit())]

    print(f"   Found {len(df)} rows, {df['TICKET ID'].nunique()} unique tickets")

    # Parse dates
    df['EVENT START TIME'] = pd.to_datetime(df['EVENT START TIME'], format='%d %b %Y %I:%M %p', errors='coerce')
    df['EVENT END TIME']   = pd.to_datetime(df['EVENT END TIME'],   format='%d %b %Y %I:%M %p', errors='coerce')

    # Parse duration
    df['duration_minutes']     = df['DURATION'].apply(parse_duration_to_minutes)
    df['duration_biz_minutes'] = df['DURATION (BUSINESS HOURS)'].apply(parse_duration_to_minutes)

    # Add useful columns
    df['created_date'] = df['EVENT START TIME'].dt.strftime('%Y-%m-%d')
    df['created_hour'] = df['EVENT START TIME'].dt.hour
    df['day_of_week']  = df['EVENT START TIME'].dt.day_name()
    df['week_number']  = df['EVENT START TIME'].dt.isocalendar().week.astype(str)
    df['month']        = df['EVENT START TIME'].dt.strftime('%Y-%m')
    df['sync_date']    = datetime.now().strftime('%Y-%m-%d')

    # Clean column names
    df = df.rename(columns={
        'TICKET ID':                  'ticket_id',
        'EVENT START TIME':           'event_start',
        'EVENT END TIME':             'event_end',
        'STATUS UPDATED FROM':        'status_from',
        'STATUS UPDATED TO':          'status_to',
        'DURATION':                   'duration_raw',
        'DURATION (BUSINESS HOURS)':  'duration_biz_raw',
        'MODIFIED BY':                'modified_by',
    })

    # Convert datetime to string for Sheets
    df['event_start'] = df['event_start'].dt.strftime('%Y-%m-%d %H:%M')
    df['event_end']   = df['event_end'].dt.strftime('%Y-%m-%d %H:%M') if 'event_end' in df.columns else ''

    # Fill NaN
    df = df.fillna('')

    return df

def write_to_sheets(df):
    print("🔗 Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(CONFIG['service_account_json'], scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(CONFIG['google_sheet_id'])

    try:
        ws = sh.worksheet(CONFIG['sheet_tab_name'])
        ws.clear()
        print(f"   Cleared existing data in '{CONFIG['sheet_tab_name']}'")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=CONFIG['sheet_tab_name'], rows=str(len(df)+10), cols=str(len(df.columns)+2))
        print(f"   Created new tab '{CONFIG['sheet_tab_name']}'")

    # Write headers + data
    data = [df.columns.tolist()] + df.values.tolist()
    ws.update(data)
    print(f"✅ Written {len(df)} rows to Google Sheets → '{CONFIG['sheet_tab_name']}' tab")
    print(f"   Columns: {list(df.columns)}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True, help='Path to your Zoho CSV export file')
    args = parser.parse_args()

    df = load_csv(args.csv)
    print()
    print("📊 Preview of data:")
    print(df.head(3).to_string())
    print()
    write_to_sheets(df)
    print()
    print("🎉 Done! Open your Google Sheet to verify the data is there.")
    print(f"   https://docs.google.com/spreadsheets/d/{CONFIG['google_sheet_id']}")

if __name__ == "__main__":
    main()
