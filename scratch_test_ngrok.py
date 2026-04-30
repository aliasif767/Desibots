import requests

data = {
    "Body": "hello via external ngrok",
    "From": "whatsapp:+1234567891"
}
try:
    response = requests.post("https://1097-119-157-141-219.ngrok-free.app/api/webhook/twilio", data=data, timeout=10)
    print("Status Code:", response.status_code)
    try:
        print("Response XML:", response.text.encode('utf-8').decode('ascii', 'ignore'))
    except Exception as e:
        print("Text error:", str(e))
except Exception as e:
    print("External Error:", str(e))
