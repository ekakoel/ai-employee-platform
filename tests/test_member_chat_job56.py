"""Job 56 — company members can advisory-chat for shared knowledge Q&A."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def test_member_can_create_conversation_and_post_message():
    set_external_client(MockExternalSystemClient())
    suffix = uuid.uuid4().hex[:8]
    co = client.post("/api/v1/companies", json={"name": f"Chat {suffix}"}).json()
    owner = client.post(
        f"/api/v1/companies/{co['id']}/users",
        json={
            "name": "Owner",
            "email": f"owner-{suffix}@c56.test",
            "role": "owner",
            "password": "demo12345",
        },
    ).json()
    oh = {"X-User-ID": owner["id"]}

    # Hire via playbook (auto-hire + operational grants)
    pb = client.post(
        f"/api/v1/companies/{co['id']}/demo/playbook-reservation",
        headers=oh,
        json={},
    )
    assert pb.status_code == 200, pb.text
    agent_id = pb.json()["agent_instance_id"]
    assert agent_id

    member = client.post(
        f"/api/v1/companies/{co['id']}/users",
        headers=oh,
        json={
            "name": "Member",
            "email": f"member-{suffix}@c56.test",
            "role": "member",
            "password": "demo12345",
        },
    ).json()
    mh = {"X-User-ID": member["id"]}

    # Seed company knowledge
    client.post(
        f"/api/v1/companies/{co['id']}/knowledge",
        headers=oh,
        json={
            "title": "Company policy leave",
            "content": "Employees receive 12 days annual leave. Contact HR for requests.",
            "category": "policy",
        },
    )

    conv = client.post(
        f"/api/v1/companies/{co['id']}/conversations",
        headers=mh,
        json={"agent_instance_id": agent_id, "title": "Ask policy"},
    )
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]

    msg = client.post(
        f"/api/v1/companies/{co['id']}/conversations/{cid}/messages",
        headers=mh,
        json={"content": "How many annual leave days do employees get?"},
    )
    assert msg.status_code == 200, msg.text
    body = msg.json()
    # response shape may be {messages: ...} or similar
    text = str(body).lower()
    assert "not allowed" not in text
    assert msg.status_code == 200


def test_require_agent_chat_in_access_module():
    from app.services.access import can_chat_with_agent, require_agent_chat

    assert callable(can_chat_with_agent)
    assert callable(require_agent_chat)
