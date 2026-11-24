import os
import tempfile
from fastapi.testclient import TestClient

# Tests validate request contracts without calling an external LLM.
os.environ.setdefault("LLM_API_KEYS", "test-key-one,test-key-two")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/lyftr-test.db")
from app.main import app

client = TestClient(app)

def test_health_contract():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert response.json()['keys_configured'] >= 2

def test_empty_message_rejected():
    response = client.post('/chat', json={'session_id': 'test-session', 'message': '   '})
    assert response.status_code == 422

def test_unknown_session():
    response = client.get('/sessions/does-not-exist/messages')
    assert response.status_code == 404
