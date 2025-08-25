from fastapi.testclient import TestClient
from main import app

def test_health_and_backtest():
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    r = c.post("/backtest", json={
        "symbol":"AAPL","strategy":"sma_cross","params":{"fast":50,"slow":200},"days":400,"include_series":True
    })
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body and ("equity" in body or "equity_index" in body)