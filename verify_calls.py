import sys
import os
from fastapi.testclient import TestClient

# Ensure the root folder is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.main import app
from app.database.db import get_db_connection

client = TestClient(app)

def test_workflow():
    print("=== Testing Temporary Call Start & Webhook ===")
    
    # 1. Start the call using the new temporary query parameter endpoint
    target_phone = "+919876543210"
    print(f"\n1. Starting call for phone number {target_phone}...")
    call_resp = client.post(f"/calls/start?phone_number={target_phone}")
    print("Response Status:", call_resp.status_code)
    call_data = call_resp.json()
    print("Response JSON (expected to fail on KYC compliance but show request mapping):", call_data)

    # 2. Add a mock call log manually to the DB to verify the webhook status update
    print("\n2. Inserting a mock call log directly to test the webhook...")
    conn = get_db_connection()
    cursor = conn.cursor()
    mock_sid = "test_call_sid_99999"
    # Clean up previous runs if any
    cursor.execute("DELETE FROM call_logs WHERE call_sid = %s", (mock_sid,))
    # Insert new mock log
    cursor.execute(
        "INSERT INTO call_logs (customer_id, campaign_id, call_sid, status) VALUES (%s, %s, %s, %s)",
        (1, 1, mock_sid, "initiated")
    )
    conn.commit()
    conn.close()
    print("Mock call log inserted successfully.")

    # 3. Test POST /webhook/twilio
    print("\n3. Testing POST /webhook/twilio...")
    webhook_payload = {
        "CallSid": mock_sid,
        "CallStatus": "completed"
    }
    web_resp = client.post("/webhook/twilio", data=webhook_payload)
    print("Response Status:", web_resp.status_code)
    web_data = web_resp.json()
    print("Response JSON:", web_data)
    
    assert web_resp.status_code == 200
    assert web_data["status"] == "success"
    assert web_data["call_log"]["status"] == "completed"
    print("Webhook processing and DB update assertion: PASS")
 
    # 4. Verify call log status directly in the database
    print("\n4. Verifying Call Log status directly in MySQL...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM call_logs WHERE call_sid = %s", (mock_sid,))
    row = cursor.fetchone()
    print("MySQL DB row status:", row["status"])
    assert row["status"] == "completed"
    conn.close()
    print("Direct DB verification assertion: PASS")

    print("\n=== Webhook and Call Verification Passed Successfully! ===")

if __name__ == '__main__':
    try:
        test_workflow()
    except Exception as e:
        print("Test failed with exception:", str(e))
        sys.exit(1)
