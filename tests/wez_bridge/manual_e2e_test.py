"""Manual E2E test: build wez_bridge payload and call ExoCore."""
import json
import sys
import tempfile
from extensions.wez_bridge.session_manager import SessionManager, Message
from extensions.wez_bridge.context_builder import ContextBuilder

# 1. Create a session
tmpdir = tempfile.mkdtemp()
sm = SessionManager(session_dir=tmpdir)
session = sm.create_session(
    first_user_message="你好，请确认 wez_bridge 对接成功",
    metadata={"pane_id": "3"},
)
sm.add_message(session.session_id, Message(
    role="agent", content="对接测试——Extension侧payload验证", metadata={}
))

# 2. Build context and payload
cb = ContextBuilder()
context = cb.build_full_context(session, host_pane_id="3")
payload = cb.build_inject_payload(
    context,
    agent_name="Alessandro",
    capture_method="terminal",
    target_storage="external_session",
)

# 3. Verify payload fields
print("=== Payload Verification ===")
print(f"  mode:        {payload['mode']}")
print(f"  client_type: {payload['client_type']}")
print(f"  source:      {payload['source']}")
print(f"  agent:       {payload['agent']}")
print(f"  messages:    {len(payload['messages'])} items")
print(f"  captured_text: {payload['captured_text'][:80]}...")
print(f"  metadata:    pane_id={payload['metadata'].get('pane_id')}")

assert payload["mode"] == "wez_bridge"
assert payload["client_type"] == "wez_bridge"
assert isinstance(payload["messages"], list)
assert len(payload["messages"]) == 2
assert payload["messages"][0]["role"] == "user"
assert isinstance(payload["captured_text"], str)
assert not payload["captured_text"].startswith("{"), "captured_text should be plain text"

print()
print("=== Calling ExoCore ===")
try:
    from config import EXOCORE_BASE_URL, EXOCORE_EXTENSION_KEY
    import requests

    url = f"{EXOCORE_BASE_URL.rstrip('/')}/api/agents/external_context_inject/"
    payload["extension_secret"] = EXOCORE_EXTENSION_KEY

    resp = requests.post(url, json=payload, timeout=30)
    print(f"  Status: {resp.status_code}")
    body = resp.json()
    print(f"  Response: {json.dumps(body, ensure_ascii=False, indent=2)}")

    assert body.get("success"), f"Expected success=True, got: {body}"
    assert body.get("session_type_used") == "wez_bridge"
    print()
    print("SUCCESS: wez_bridge E2E对接完成！")
    if "external_session_id" in body:
        print(f"  external_session_id: {body['external_session_id']}")
    print(f"  session_type_used:  {body['session_type_used']}")
    print(f"  compacted_up_to:    {body.get('compacted_up_to')}")

except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)
