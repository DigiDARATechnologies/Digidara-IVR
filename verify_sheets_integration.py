import sys
import os
import re
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure the root folder is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.main import app
from app.database.db import get_db_connection
from app.services import google_sheets_service

client = TestClient(app)

def test_google_sheet_normalization_and_fallback():
    print("=== 1. Testing Google Sheets Header & Data Normalization ===")
    
    # Define a sample CSV response with variations of headers
    mock_csv_content = (
        "Customer Name,Ph. No,Preferred Language,Call Status\n"
        "Alice Smith,+919999988888,English,pending\n"
        "Bob Jones,1234567890,Tamil,no-answer\n"
    )
    
    class MockResponse:
        status_code = 200
        content = mock_csv_content.encode("utf-8")

    # Patch requests.get to simulate public sheet CSV export download
    with patch("requests.get", return_value=MockResponse()) as mock_get:
        rows = google_sheets_service.read_sheet_data("https://docs.google.com/spreadsheets/d/12345/edit")
        
        # Verify URL rewrite for export
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        print("CSV Export Rewrite URL:", called_url)
        assert "/export?format=csv" in called_url

        # Check normalization
        assert len(rows) == 2
        print("Parsed Row 1:", rows[0])
        assert rows[0]["name"] == "Alice Smith"
        assert rows[0]["phone"] == "+919999988888"
        assert rows[0]["language"] == "English"
        assert rows[0]["status"] == "pending"
        assert rows[0]["row_number"] == 2

        print("Parsed Row 2:", rows[1])
        assert rows[1]["name"] == "Bob Jones"
        assert rows[1]["phone"] == "1234567890"
        assert rows[1]["language"] == "Tamil"
        assert rows[1]["status"] == "no-answer"
        assert rows[1]["row_number"] == 3

    print("Google Sheets Normalization and Fallback testing: PASS\n")

def test_run_sheet_endpoint():
    print("=== 2. Testing /calls/run-sheet API Endpoint ===")
    
    # 1. Clean up potential customer and log records from previous runs
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM call_logs WHERE sheet_url = %s", ("https://docs.google.com/spreadsheets/d/test_run_sheet/edit",))
    cursor.execute(
        "DELETE FROM customers WHERE email IN (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            "919999988888@example.com", "1234567890@example.com", "919876543210@example.com",
            "917777777777@example.com", "916666666666@example.com", "915555555555@example.com",
            "914444444444@example.com", "913333333333@example.com", "912222222222@example.com"
        )
    )
    
    # Let's verify campaign ID 1 exists, if not we will create a mock campaign
    cursor.execute("SELECT id FROM campaigns LIMIT 1")
    camp = cursor.fetchone()
    if camp:
        campaign_id = camp["id"]
    else:
        cursor.execute("INSERT INTO campaigns (campaign_name, objective, ai_prompt) VALUES (%s, %s, %s)", 
                       ("Sheet Campaign", "Recall patients", "Hello {name}, you chose {language}."))
        campaign_id = cursor.lastrowid
        
    conn.commit()
    conn.close()

    mock_sheet_rows = [
        {"row_number": 2, "name": "Alice Smith", "phone": "+919999988888", "language": "English", "status": "pending"},
        {"row_number": 3, "name": "Bob Jones", "phone": "1234567890", "language": "Tamil", "status": "no-answer"},
        {"row_number": 4, "name": "Charlie Brown", "phone": "+919876543210", "language": "English", "status": "completed"},
        {"row_number": 5, "name": "Dave Miller", "phone": "+917777777777", "language": "English", "status": "no answered"},
        {"row_number": 6, "name": "Eve Davis", "phone": "+916666666666", "language": "Tamil", "status": "no answer"},
        {"row_number": 7, "name": "Frank Wilson", "phone": "+915555555555", "language": "English", "status": "not answered"},
        {"row_number": 8, "name": "Grace Lee", "phone": "+914444444444", "language": "Tamil", "status": "busy"},
        {"row_number": 9, "name": "Heidi Chen", "phone": "+913333333333", "language": "English", "status": "failed"},
        {"row_number": 10, "name": "Ivan Kovac", "phone": "+912222222222", "language": "Tamil", "status": ""}
    ]

    # Patch read_sheet_data to return our mock rows
    with patch("app.services.google_sheets_service.read_sheet_data", return_value=mock_sheet_rows):
        payload = {
            "sheet_url": "https://docs.google.com/spreadsheets/d/test_run_sheet/edit",
            "campaign_id": campaign_id
        }
        # Run sheet endpoint and verify only the first call is triggered
        with patch("app.services.google_sheets_service.update_sheet_feedback") as mock_sheet_update:
            response = client.post("/calls/run-sheet", json=payload)
            print("Response Status:", response.status_code)
            print("Response JSON:", response.json())
            
            assert response.status_code == 200
            data = response.json()
            assert "Triggered call for row 2 and queued 5 other call(s)" in data["message"]
            assert len(data["calls_triggered"]) == 1

    # 2. Verify database records
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify customer created for the triggered call (Alice Smith)
    cursor.execute("SELECT * FROM customers WHERE email = %s", ("919999988888@example.com",))
    cust = cursor.fetchone()
    assert cust is not None, "Expected customer Alice Smith to be created"
    assert cust["name"] == "Alice Smith"

    # Verify other customers were NOT created yet (they are in the queue)
    for email in ["1234567890@example.com", "917777777777@example.com", "916666666666@example.com"]:
        cursor.execute("SELECT * FROM customers WHERE email = %s", (email,))
        assert cursor.fetchone() is None
        
    # Verify only 1 call log created
    cursor.execute("SELECT * FROM call_logs WHERE sheet_url = %s", ("https://docs.google.com/spreadsheets/d/test_run_sheet/edit",))
    logs = cursor.fetchall()
    assert len(logs) == 1
    
    conn.close()
    print("API Endpoint and DB creation testing: PASS\n")

def test_webhook_feedback_flow():
    print("=== 3. Testing Webhook Callback Sheet Write-back flow ===")
    
    # Grab one call log created by the previous step to trigger webhook
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT call_sid, campaign_id FROM call_logs WHERE sheet_url = %s LIMIT 1", 
                   ("https://docs.google.com/spreadsheets/d/test_run_sheet/edit",))
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    call_sid = row["call_sid"]
    campaign_id = row["campaign_id"]
    
    # We patch update_sheet_feedback and trigger_next_queued_call to verify they are called when webhook finishes
    with patch("app.services.google_sheets_service.update_sheet_feedback") as mock_update, \
         patch("app.services.twilio_service.trigger_next_queued_call") as mock_trigger:
        webhook_payload = {
            "CallSid": call_sid,
            "CallStatus": "completed",
            "CallDuration": "45"
        }
        response = client.post("/webhook/twilio", data=webhook_payload)
        assert response.status_code == 200
        print("Webhook call response status:", response.status_code)
        
        # Since the sheet feedback runs in a background thread, we wait a moment or join threads
        import time
        for _ in range(10):
            if mock_update.called and mock_trigger.called:
                break
            time.sleep(0.2)
            
        assert mock_update.called
        assert mock_trigger.called
        
        # Verify mock_trigger args
        mock_trigger.assert_called_once_with("https://docs.google.com/spreadsheets/d/test_run_sheet/edit", campaign_id)
        
        args, kwargs = mock_update.call_args
        print("google_sheets_service.update_sheet_feedback called with:")
        print("  Sheet URL:", args[0])
        print("  Row Number:", args[1])
        print("  Feedback Data:", args[2])
        
        assert args[0] == "https://docs.google.com/spreadsheets/d/test_run_sheet/edit"
        assert args[2]["status"] == "completed"
        assert args[2]["duration"] == "45"

    print("Webhook Callback Sheet Write-back testing: PASS\n")

if __name__ == '__main__':
    try:
        test_google_sheet_normalization_and_fallback()
        test_run_sheet_endpoint()
        test_webhook_feedback_flow()
        print("=== ALL TESTS PASSED SUCCESSFULLY ===")
    except Exception as e:
        print("Test failed with exception:", str(e))
        sys.exit(1)

