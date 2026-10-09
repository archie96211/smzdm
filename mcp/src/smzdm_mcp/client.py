"""Small, fixed-origin client. Credentials never enter tool results."""
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class APIError(Exception):
    pass


def load_config():
    path = Path(os.getenv("SMZDM_MCP_CONFIG", Path.home() / ".config/smzdm-mcp/config.json"))
    data = json.loads(path.read_text()) if path.exists() else {}
    url = os.getenv("SMZDM_URL", data.get("url", "http://127.0.0.1:18087"))
    token = os.getenv("SMZDM_API_TOKEN", "")
    token_file = os.getenv("SMZDM_API_TOKEN_FILE", data.get("token_file", ""))
    if token_file:
        token = Path(token_file).expanduser().read_text().strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise APIError("Invalid service URL in private configuration")
    if not token:
        raise APIError("Configure the API token outside the repository")
    ca_file = os.getenv("SMZDM_CA_FILE", data.get("ca_file", ""))
    verify = ssl.create_default_context(cafile=str(Path(ca_file).expanduser())) if ca_file else True
    return url.rstrip("/") + "/api/v1/", token, verify


class API:
    def __init__(self, url, token, transport=None, verify=True):
        self.client = httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {token}"},
                                       timeout=30, follow_redirects=False, transport=transport, verify=verify)

    async def request(self, method, path, data=None, request_id=None):
        headers = {"Idempotency-Key": request_id} if request_id else {}
        try:
            response = await self.client.request(method, path, json=data, headers=headers)
        except httpx.HTTPError:
            raise APIError("Service unavailable or request timed out. Read back state before retrying a write; reuse the creation request_id.") from None
        if response.status_code >= 300:
            # Never echo a response body: legacy servers may include input secrets.
            messages = {401: "Authentication failed", 403: "Access denied", 404: "Resource not found",
                        409: "Conflict: inspect existing state or use the original request_id and payload",
                        422: "Invalid input or missing notification configuration", 503: "Service not configured"}
            raise APIError(messages.get(response.status_code, "Service request failed"))
        try:
            return response.json()
        except ValueError:
            raise APIError("Service returned invalid JSON") from None

    async def close(self):
        await self.client.aclose()
