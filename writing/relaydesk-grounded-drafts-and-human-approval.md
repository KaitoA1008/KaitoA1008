# Grounded drafts and human approval in the RelayDesk API

By Quang Anh Nguyen

A support assistant can find the right policy and still take the wrong action. A policy may change while a person reviews a draft, or the person approving it may lack permission. RelayDesk separates preparing a response from authorizing and executing a change so those checks can happen at the right time.

This walkthrough follows a damaged-delivery request through three examples: approving a sandbox return, refusing an approval after its policy changes, and enforcing reviewer permissions. RelayDesk is an independent portfolio application using a fictional store and synthetic customers, orders and policies. Its return requests are sandbox records; they do not issue real refunds or send customer messages.

## Follow the approval boundary

The workflow checks the order context, retrieves active policy sources, prepares a draft and proposes an action. A LangGraph interrupt pauses the workflow before execution. The draft and its proposed action remain available for review.

```text
Check context -> Retrieve policy -> Prepare draft -> Propose action
                                                         |
                                                  Await approval
                                                         |
                                        Recheck conditions -> Execute
```

Policy retrieval combines PostgreSQL full-text ranking with vector ranking. The default vectors are local hashed features, with an optional local embedding model. The source record and version travel with the proposal. Finding a passage does not authorize a write, and a citation alone does not prove every sentence in a response is correct.

## Prepare a local demo

The examples require a running RelayDesk API and worker in local demo authentication mode at `http://127.0.0.1:8004`. The full application source is currently private; this public sample contains the integration examples, not a standalone installation of the product. Product captures and an overview are available in the [RelayDesk portfolio walkthrough](https://contra.com/community/PHRcxPwP-relay-desk-support-workspace-with-human-approved-ai).

With that local environment running, install `httpx` and run the [complete example script](relaydesk-api-examples.py):

```powershell
python -m pip install httpx
python writing/relaydesk-api-examples.py
```

Each example calls `POST /v1/session` using its own cookie client, which creates a separate seeded demo workspace. The helper submits a damaged-delivery ticket and polls until its queued draft reaches `awaiting_approval`. It raises an error if the worker does not finish within 45 seconds.

Demo session creation and role switching are local QA facilities. An account-mode integration needs its own authenticated session, workspace membership and CSRF handling.

## Example 1 Approve a grounded proposal once

Before approving, inspect both the proposed action and the cited policy. In the seeded damaged-delivery example, the draft cites “Damaged deliveries” and states its seven-day reporting window. At this stage, `GET /v1/returns` is empty.

The relevant part of `grounded_return()` is:

```python
action = detail["action"]
decision = {"expected_version": action["version"], "decision": "approve"}
result = read(client.post(f"actions/{action['id']}/decision", json=decision))
repeated = read(client.post(f"actions/{action['id']}/decision", json=decision))

assert result["state"] == "succeeded" and result["receipt"]
assert repeated["receipt"] == result["receipt"]
```

The API checks the action version and the execution conditions before creating the sandbox record. Repeating the same approval returns the stored receipt. The complete example also checks that exactly one sandbox return exists.

The script approves this fixed synthetic case automatically to exercise the contract. A product integration should present the proposal and its evidence to the reviewer before sending the decision.

## Example 2 Refuse a proposal with a stale policy

A proposal may be valid when drafted and invalid when approved. `stale_policy()` first creates a fresh proposal, then deactivates the cited policy using its current version:

```python
read(client.post(f"knowledge/{source['id']}/publish", json={
    "expected_version": source["version"], "active": False,
}))
response = client.post(f"actions/{action['id']}/decision", json={
    "expected_version": action["version"], "decision": "approve",
})
assert response.status_code == 409
assert not read(client.get("returns"))
```

The result is a conflict, with no return created. Showing the old citation is insufficient: execution must check whether the source is still active and current. On a `409`, reload the case and review a fresh proposal instead of blindly resending the old approval.

## Example 3 Enforce reviewer permissions

A valid proposal still needs an authorized decision. In `reviewer_permissions()`, demo role switching changes the current workspace role to `operator`. The approval request returns `403`:

```python
read(client.post("session/role", json={"role": "operator"}))
response = client.post(path, json={
    "expected_version": action["version"], "decision": "approve",
})
assert response.status_code == 403
```

The example then switches to `reviewer` and rejects the proposal. The action becomes `rejected`, and the return list remains empty. This distinguishes authorization failure from a legitimate reviewer decision. Production deployments can additionally require a reviewer other than the person who initiated the work.

## Check the result and its limits

The three examples were executed successfully against the local synthetic demo on 11 November 2026. Their expected output is:

```text
PASS grounded_return: one sandbox return; repeated approval reused the receipt.
PASS stale_policy: approval returned 409; no return was created.
PASS reviewer_permissions: operator blocked; reviewer rejected the proposal.
```

These examples verify specific API behavior. They do not establish general model accuracy, full prompt-injection protection or successful integration with a real support system. Drafts default to local templates; a live language model is not required for this walkthrough.

For an integration, distinguish the reviewer decision from its execution result. A runtime failure can leave an action recovering rather than complete. Inspect the action state and receipt before reporting success, and agree how the client should poll or receive updates while recovery proceeds.
