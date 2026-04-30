import requests

data = {
    "Body": "hello from python",
    "From": "whatsapp:+1234567890"
}
try:
    response = requests.post("http://localhost:8000/api/webhook/twilio", data=data)
    print("Status Code:", response.status_code)
    print("Response Body:", response.text)
except Exception as e:
    print("Error:", str(e))
