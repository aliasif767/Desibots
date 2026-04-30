import requests

BASE_URL = "http://localhost:8000/api/v1" # Assuming it runs on 8000

def test_available_doctors():
    try:
        res = requests.get(f"{BASE_URL}/doctors/available?type=heart_attack")
        if res.status_code == 200:
            data = res.json()
            print("Doctors Found:", data['count'])
            for doc in data['doctors']:
                print(f"Name: {doc.get('doctor_name')}")
                print(f"Specialty: {doc.get('specialty')}")
                print(f"Available Days: {doc.get('available_days')}")
                print("-" * 20)
        else:
            print(f"Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_available_doctors()
