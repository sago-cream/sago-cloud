"""Issue a separate MCP OAuth grant using a fresh local, one-use pairing code.

The only stdout is the private credential document, intended for a pipe into
bot-core's state volume. Never invoke this script in a logged terminal directly.
"""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request

origin = "http://127.0.0.1:3773"
resource = origin + "/mcp"
redirect_uri = "http://127.0.0.1:38471/callback"

def post(path, payload, form=False):
    data = urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode()
    request = urllib.request.Request(origin + path, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded" if form else "application/json",
        "Origin": origin,
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        failure = json.load(error)
        raise RuntimeError(f"T3 OAuth request rejected ({error.code}): {failure.get('message', failure.get('error', 'invalid request'))}") from None

client = post("/oauth/mcp/register", {"client_name": "MiniSago Discord coding",
    "redirect_uris": [redirect_uri], "grant_types": ["authorization_code"],
    "response_types": ["code"], "token_endpoint_auth_method": "none"})
verifier = secrets.token_urlsafe(48)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
state = secrets.token_urlsafe(24)
authorization = {"response_type": "code", "client_id": client["client_id"],
    "redirect_uri": redirect_uri, "code_challenge": challenge,
    "code_challenge_method": "S256", "state": state, "resource": resource}
pairing = json.loads(subprocess.check_output(["t3", "auth", "pairing", "create",
    "--ttl", "1m", "--label", "MiniSago OAuth setup", "--json"]))
approval = post("/oauth/mcp/decision", {"authorization": authorization,
    "decision": {"_tag": "pairing-code", "access": "full-access", "code": pairing["credential"]}})
callback = urllib.parse.urlparse(approval["redirectTo"])
params = urllib.parse.parse_qs(callback.query)
if params.get("state") != [state]:
    raise RuntimeError("T3 OAuth state mismatch")
tokens = post("/oauth/mcp/token", {"grant_type": "authorization_code", "code": params["code"][0],
    "client_id": client["client_id"], "redirect_uri": redirect_uri,
    "code_verifier": verifier, "resource": resource}, form=True)
# Check the issued audience before replacing the bot's current grant.
headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer " + tokens["access_token"], "mcp-protocol-version": "2025-06-18"}
for request_id, method, payload in [(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "MiniSago grant check", "version": "1"}}),
        (2, "tools/call", {"name": "t3_project_list", "arguments": {"limit": 1}})]:
    request = urllib.request.Request(resource, data=json.dumps({"jsonrpc": "2.0", "id": request_id,
        "method": method, "params": payload}).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.headers.get("Mcp-Session-Id"):
                headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:500]
        raise RuntimeError(f"T3 MCP check {method} rejected ({error.code}): {detail}") from None
    if result.get("error") or result.get("result", {}).get("isError"):
        raise RuntimeError("The new T3 grant could not read projects")
json.dump({"serverUrl": os.environ.get("MINISAGO_BOT_T3_URL", "http://t3:3773/mcp"),
    "redirectUrl": redirect_uri, "client": client, "tokens": tokens}, sys.stdout)
