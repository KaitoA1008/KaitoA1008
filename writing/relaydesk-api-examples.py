"""Three executable examples for RelayDesk's local synthetic demo API.

Install httpx and start RelayDesk in demo auth mode before running this file.
Each example creates a separate seeded workspace. No real customer system is used.
"""

from contextlib import contextmanager
import time

import httpx


BASE_URL = "http://127.0.0.1:8004/v1/"


def read(response):
    response.raise_for_status()
    return response.json()


@contextmanager
def demo_client():
    with httpx.Client(base_url=BASE_URL, timeout=45) as client:
        read(client.post("session"))
        yield client


def draft_damage(client):
    ticket = read(client.post("tickets", json={
        "subject": "Damaged organizer",
        "message": "My organizer arrived damaged yesterday. Can I return it?",
    }))
    path = f"tickets/{ticket['id']}"
    read(client.post(f"{path}/runs", json={"expected_version": ticket["version"]}))
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        detail = read(client.get(path))
        if detail.get("run", {}).get("state") not in (None, "queued", "running"):
            assert detail["run"]["state"] == "awaiting_approval", detail["run"]
            return detail
        time.sleep(0.2)
    raise TimeoutError("Check the API and worker before retrying the example.")


def grounded_return():
    with demo_client() as client:
        detail = draft_damage(client)
        assert detail["run"]["sources"][0]["title"] == "Damaged deliveries"
        assert "7 days" in detail["run"]["draft"]
        assert not read(client.get("returns"))

        action = detail["action"]
        decision = {"expected_version": action["version"], "decision": "approve"}
        result = read(client.post(f"actions/{action['id']}/decision", json=decision))
        assert result["state"] == "succeeded" and result["receipt"]
        repeated = read(client.post(f"actions/{action['id']}/decision", json=decision))
        assert repeated["receipt"] == result["receipt"]
        returns = read(client.get("returns"))
        assert len(returns) == 1 and returns[0]["sandbox"]
    print("PASS grounded_return: one sandbox return; repeated approval reused the receipt.")


def stale_policy():
    with demo_client() as client:
        detail = draft_damage(client)
        source = next(item for item in read(client.get("knowledge"))
                      if item["title"] == "Damaged deliveries")
        read(client.post(f"knowledge/{source['id']}/publish", json={
            "expected_version": source["version"], "active": False,
        }))
        action = detail["action"]
        response = client.post(f"actions/{action['id']}/decision", json={
            "expected_version": action["version"], "decision": "approve",
        })
        assert response.status_code == 409, response.text
        assert not read(client.get("returns"))
    print("PASS stale_policy: approval returned 409; no return was created.")


def reviewer_permissions():
    with demo_client() as client:
        detail = draft_damage(client)
        action = detail["action"]
        path = f"actions/{action['id']}/decision"
        read(client.post("session/role", json={"role": "operator"}))
        response = client.post(path, json={
            "expected_version": action["version"], "decision": "approve",
        })
        assert response.status_code == 403, response.text

        read(client.post("session/role", json={"role": "reviewer"}))
        result = read(client.post(path, json={
            "expected_version": action["version"], "decision": "reject",
        }))
        assert result["state"] == "rejected"
        assert not read(client.get("returns"))
    print("PASS reviewer_permissions: operator blocked; reviewer rejected the proposal.")


def main():
    grounded_return()
    stale_policy()
    reviewer_permissions()


if __name__ == "__main__":
    main()
