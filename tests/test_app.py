import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

def test_app_exists():
    assert app is not None

def test_app_is_testing():
    app.config['TESTING'] = True
    client = app.test_client()
    response = client.get('/')
    assert response.status_code in (200, 302)  # 302 if it redirects to login etc.

def test_health_endpoint():
    app.config['TESTING'] = True
    client = app.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'healthy'