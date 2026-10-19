"""Job 56 — company members can advisory-chat for shared knowledge Q&A."""

from fastapi.testclient import TestClient

from app.main import app
from app.tools.connectors import MockExternalSystemClient, set_external_client

client = TestClient(app)


def _auth_headers(email: str, password: str = "demo12345") -> dict:
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert tok.status_code == 200, tok.text
    body = tok.json()
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "X-User-ID": body["user_id"],
    }


def test_member_can_create_conversation_and_post_message():
    set_external_client(MockExternalSystemClient())
    demo = client.post("/api/v1/demo/bootstrap").json()
    assert demo.get("company_id"), demo
    company_id = demo["company_id"]
    owner_h = _auth_headers(demo["owner_email"])

    member = next(u for u in demo["users"] if u["role"] == "reservation")
    # reservation is operational; also try pure member if present
    member_candidates = [u for u in demo["users"] if u["role"] in {"member", "reservation"}]
    member = member_candidates[0]
    member_h = _auth_headers(member["email"])

    # Ensure agent exists (bootstrap may hire)
    agents = client.get(f"/api/v1/companies/{company_id}/agents", headers=owner_h)
    assert agents.status_code == 200, agents.text
    agent_list = agents.json()
    if not agent_list:
        # playbook hires if needed
        pb = client.post(
            f"/api/v1/companies/{company_id}/demo/playbook-reservation",
            headers=owner_h,
            json={},
        )
        assert pb.status_code == 200, pb.text
        agent_id = pb.json()["agent_instance_id"]
    else:
        agent_id = agent_list[0]["id"]

    # Seed knowledge as owner
    client.post(
        f"/api/v1/companies/{company_id}/knowledge",
        headers=owner_h,
        json={
            "title": "Company policy leave",
            "content": "Employees receive 12 days annual leave. Contact HR for requests.",
            "category": "policy",
        },
    )

    conv = client.post(
        f"/api/v1/companies/{company_id}/conversations",
        headers=member_h,
        json={"agent_instance_id": agent_id, "title": "Ask policy"},
    )
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]

    msg = client.post(
        f"/api/v1/companies/{company_id}/conversations/{cid}/messages",
        headers=member_h,
        json={"content": "How many annual leave days do employees get?"},
    )
    assert msg.status_code == 200, msg.text
    assert "not allowed" not in msg.text.lower()


def test_require_agent_chat_in_access_module():
    from app.services.access import can_chat_with_agent, require_agent_chat

    assert callable(can_chat_with_agent)
    assert callable(require_agent_chat)
