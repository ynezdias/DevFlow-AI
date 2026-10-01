from tests.support import *

pytestmark = pytest.mark.usefixtures("database", "publisher", "webhook_secret")

def test_dashboard_history_metrics_and_cors(database):
    first = send_event(pr_payload()).json()["review_id"]
    payload = pr_payload()
    payload["pull_request"]["head"]["sha"] = "d" * 40
    second = send_event(payload).json()["review_id"]
    # The fixture shares one transaction: PostgreSQL now() can tie timestamps.
    # Set explicit ordering rather than relying on random UUID ordering.
    from datetime import datetime, timezone, timedelta
    from uuid import UUID
    database.get(ReviewJob, UUID(first)).created_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    database.get(ReviewJob, UUID(second)).created_at = datetime.now(timezone.utc)
    database.flush()
    page1 = client.get("/api/reviews?page=1&page_size=1").json()
    page2 = client.get("/api/reviews?page=2&page_size=1").json()
    assert page1["items"][0]["id"] == second
    assert page2["items"][0]["id"] == first
    assert "changed_files" not in page1["items"][0]
    assert client.get("/api/reviews?page=0").status_code == 422
    assert client.get("/api/reviews?page_size=101").status_code == 422
    metrics = client.get("/api/metrics/summary").json()
    assert metrics["total_reviews"] == sum(metrics[k] for k in ["completed","queued","processing","failed","superseded"])
    assert metrics["queued"] >= 2
    good = client.get("/api/reviews", headers={"Origin":"http://localhost:5173"})
    assert good.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.get("/api/reviews", headers={"Origin":"https://untrusted.example"})
    assert "access-control-allow-origin" not in bad.headers
    assert "Server-Timing" in good.headers


def test_create_get_duplicate_and_validation():
    payload = {"repository_name": "test/" + str(uuid4()), "pull_request_number": 1, "head_sha": "a"*40}
    created = client.post("/api/reviews", json=payload)
    assert created.status_code == 201
    review_id = created.json()["id"]
    assert client.get(f"/api/reviews/{review_id}").json()["repository_name"] == payload["repository_name"]
    assert client.post("/api/reviews", json=payload).status_code == 409
    assert client.get(f"/api/reviews/{uuid4()}").status_code == 404
    assert client.post("/api/reviews", json={**payload, "pull_request_number":0}).status_code == 422
