import requests
import json
import random
from dotenv import load_dotenv

load_dotenv()

test_email = f"test.user.{random.randint(100000, 999999)}@gmail.com"
payload = {
    "email": test_email,
    "password": "TestPassword123",
    "name": "Test User",
    "role": "patient"
}

print(f"Testing signup-send-otp with email: {test_email}")
response = requests.post("http://127.0.0.1:8000/auth/signup-send-otp", json=payload)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")

# Test forgot password OTP
print("\n" + "="*50)
test_email_forgot = "karthicksaravanan0703@gmail.com"
print(f"Testing forgot-password with email: {test_email_forgot}")
response2 = requests.post("http://127.0.0.1:8000/auth/forgot-password", data={"email": test_email_forgot})
print(f"Status Code: {response2.status_code}")
print(f"Response: {response2.json()}")
