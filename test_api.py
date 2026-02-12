import requests
from requests.auth import HTTPBasicAuth

BASE_URL = "http://127.0.0.1:8000"
USER = "admin"
PASSWORD = "85258525dD"

def test_me():
    resp = requests.get(f"{BASE_URL}/api/me", auth=HTTPBasicAuth(USER, PASSWORD))
    print("/api/me", resp.status_code, resp.json())

def test_health():
    resp = requests.get(f"{BASE_URL}/health")
    print("/health", resp.status_code, resp.json())

def test_home_data():

    resp = requests.get(f"{BASE_URL}/home-data", auth=HTTPBasicAuth(USER, PASSWORD))
    print("/home-data", resp.status_code, resp.json())

def test_courses():
    resp = requests.get(f"{BASE_URL}/courses", auth=HTTPBasicAuth(USER, PASSWORD))
    print("/courses", resp.status_code)
    try:
        data = resp.json()
        print("Cursos encontrados:", len(data) if isinstance(data, list) else data)
    except Exception as e:
        print("Erro ao decodificar resposta de /courses:", e)

if __name__ == "__main__":
    test_me()
    test_health()
    test_home_data()
    test_courses()
