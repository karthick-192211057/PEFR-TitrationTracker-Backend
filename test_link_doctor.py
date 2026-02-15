import requests
import json

# Test the link-doctor endpoint
doctor_email = "jandajanda0709@gmail.com"
patient_email = "karthicksaravanan0703@gmail.com"  # Use a patient email for testing
patient_password = "TestPassword123"

# First, login as patient using OAuth2PasswordRequestForm format
login_response = requests.post("http://127.0.0.1:8000/auth/login", data={
    "username": patient_email,  # OAuth2PasswordRequestForm expects 'username'
    "password": patient_password
})

print(f"Login Status: {login_response.status_code}")
if login_response.status_code == 200:
    token_data = login_response.json()
    access_token = token_data.get("access_token")
    print(f"Token obtained: {access_token[:20]}...")
    
    # Now test the link-doctor endpoint
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "doctor_email": doctor_email
    }
    
    response = requests.post(
        "http://127.0.0.1:8000/patient/link-doctor",
        json=payload,
        headers=headers
    )
    
    print(f"\nLink Doctor Status: {response.status_code}")
    print(f"Response: {response.json()}")
else:
    print(f"Login failed: {login_response.json()}")
