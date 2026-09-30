from tests.support import *

pytestmark = pytest.mark.usefixtures("database", "publisher", "webhook_secret")

def test_delivery_deduplicated(database):
    delivery = str(uuid4())
    first = send_event(pr_payload(), delivery=delivery)
    second = send_event(pr_payload(), delivery=delivery)
    assert first.status_code == 202
    assert second.json() == {"status": "duplicate"}
    assert database.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.delivery_id == delivery)) == 1


def test_distinct_deliveries_same_commit(database):
    first = send_event(pr_payload()).json()
    second = send_event(pr_payload("reopened")).json()
    assert first["review_id"] == second["review_id"]
    assert database.scalar(select(func.count()).select_from(ReviewJob).where(
        ReviewJob.repository_name == "ynezdias/devflow-test",
        ReviewJob.pull_request_number == 7, ReviewJob.head_sha == "a" * 40,
    )) == 1


def test_ignored_delivery_persisted(database):
    delivery = str(uuid4())
    assert send_event({"action": "closed"}, delivery=delivery).json() == {"status": "ignored"}
    assert send_event({"action": "closed"}, delivery=delivery).json() == {"status": "duplicate"}
    assert database.get(WebhookEvent, delivery).status == "ignored"


def test_replay_many_webhooks_one_job(database):
    delivery=str(uuid4())
    responses=[send_event(pr_payload(),delivery=delivery) for _ in range(10)]
    assert responses[0].status_code==202
    assert all(r.json()["status"]=="duplicate" for r in responses[1:])
    assert database.scalar(select(func.count()).select_from(ReviewJob).where(ReviewJob.repository_name=="ynezdias/devflow-test", ReviewJob.pull_request_number==7, ReviewJob.head_sha=="a"*40))==1
