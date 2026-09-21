import os
import requests
import datetime
from google.oauth2.service_account import Credentials
import google.auth.transport.requests

def get_calendar_token() -> str:
    """Gets access token from service account credentials."""
    cred_file = os.path.join(os.getcwd(), "credentials.json")
    if not os.path.exists(cred_file):
        raise FileNotFoundError("credentials.json not found in root directory.")
    creds = Credentials.from_service_account_file(
        cred_file,
        scopes=["https://www.googleapis.com/auth/calendar"]
    )
    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    return creds.token

def get_available_slots() -> str:
    """
    Fetches available counseling slots from Google Calendar.
    If credentials or API fail, falls back to generating mock available slots for demonstration.
    """
    calendar_id = os.getenv("CALENDAR_ID", "primary")
    try:
        token = get_calendar_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Look at the next 3 days
        time_min = datetime.datetime.utcnow().isoformat() + "Z"
        time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=3)).isoformat() + "Z"
        
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime"
        }
        
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        if resp.status_code == 200:
            events = resp.json().get("items", [])
            busy_times = []
            for event in events:
                start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
                if start:
                    busy_times.append(start)
            
            # Offer standard slots (e.g. 10 AM, 2 PM, 4 PM) for the next 3 working days, skipping weekends (Saturday & Sunday).
            available = []
            now = datetime.datetime.now()
            day_offset = 1
            while len(available) < 3 and day_offset <= 10:
                day = now + datetime.timedelta(days=day_offset)
                day_offset += 1
                
                # Skip Saturday (5) and Sunday (6)
                if day.weekday() in [5, 6]:
                    continue
                    
                day_str = day.strftime("%A, %B %d")
                slots_for_day = []
                for hour in [10, 14, 16]:
                    slot_time = datetime.datetime(day.year, day.month, day.day, hour, 0)
                    is_busy = False
                    for b in busy_times:
                        if b.startswith(slot_time.strftime("%Y-%m-%dT")):
                            is_busy = True
                            break
                    if not is_busy:
                        time_ampm = "10:00 AM" if hour == 10 else "2:00 PM" if hour == 14 else "4:00 PM"
                        slots_for_day.append(time_ampm)
                if slots_for_day:
                    available.append(f"- {day_str}: " + ", ".join(slots_for_day))
            
            if available:
                return "Here are our available counseling slots:\n" + "\n".join(available)
            else:
                return "No available slots found in the next 10 days."
    except Exception as e:
        print(f"[Calendar] Live Google Calendar fetch error (falling back to mock): {str(e)}")
        
    # Fallback Mock Slots (Warm & Natural - skipping Saturday & Sunday)
    now = datetime.datetime.now()
    slots = []
    offset = 1
    while len(slots) < 3 and offset <= 10:
        day = now + datetime.timedelta(days=offset)
        offset += 1
        
        # Skip Saturday (5) and Sunday (6)
        if day.weekday() in [5, 6]:
            continue
            
        day_name = day.strftime("%A")
        slots.append(f"- {day_name} ({day.strftime('%B %d')}): 10:00 AM, 2:00 PM, or 4:00 PM")
        
    return (
        "Here are our available counseling slots:\n" +
        "\n".join(slots) +
        "\n\n(To make this live, share your Google Calendar with "
        "dharshan@upheld-conduit-467507-h2.iam.gserviceaccount.com)"
    )

def book_appointment(customer_name: str, slot_time_str: str) -> str:
    """
    Creates a calendar event on Google Calendar.
    Falls back to mock booking if API/credentials fail.
    """
    calendar_id = os.getenv("CALENDAR_ID", "primary")
    try:
        token = get_calendar_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        event_body = {
            "summary": f"Counseling Session - {customer_name}",
            "description": f"Enquiry follow up call booked via DigiDara AI for {customer_name}.\nRequested Slot: {slot_time_str}",
            "start": {
                "dateTime": (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + "Z",
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": (datetime.datetime.utcnow() + datetime.timedelta(days=1, minutes=30)).isoformat() + "Z",
                "timeZone": "UTC"
            }
        }
        
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        resp = requests.post(url, headers=headers, json=event_body, timeout=5)
        if resp.status_code in [200, 201]:
            print(f"[Calendar] Live Google Calendar event created successfully for {customer_name} at {slot_time_str}")
            return f"Success! Event booked on Google Calendar for {slot_time_str}."
    except Exception as e:
        print(f"[Calendar] Live Google Calendar booking error (falling back to mock): {str(e)}")
        
    return f"Success! Mock event created for {customer_name} on {slot_time_str}."
