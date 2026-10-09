import asyncio
import httpx
import pytest
from smzdm_mcp.client import API, APIError


def test_private_errors_do_not_reach_model():
    async def run():
        async def handle(request):
            assert request.headers['authorization'] == 'Bearer private-token'
            return httpx.Response(422, json={'detail': 'private-url/private-key'})
        api = API('http://localhost/api/v1/', 'private-token', httpx.MockTransport(handle))
        try:
            with pytest.raises(APIError) as exc:
                await api.request('PATCH', 'bark', {'secret': 'test'})
            assert 'private-' not in str(exc.value)
        finally:
            await api.close()
    asyncio.run(run())


def test_redirects_are_not_followed():
    async def run():
        calls = []
        async def handle(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': 'https://other.example'})
        api = API('http://localhost/api/v1/', 'private-token', httpx.MockTransport(handle))
        try:
            with pytest.raises(APIError): await api.request('GET', 'status')
            assert len(calls) == 1
        finally: await api.close()
    asyncio.run(run())


def test_custom_ca_rejects_missing_certificate(tmp_path, monkeypatch):
    import json
    from smzdm_mcp.client import load_config
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'url': 'https://monitor.example', 'ca_file': str(tmp_path / 'missing.crt')}))
    monkeypatch.setenv('SMZDM_MCP_CONFIG', str(config))
    monkeypatch.setenv('SMZDM_API_TOKEN', 'test-token')
    monkeypatch.delenv('SMZDM_API_TOKEN_FILE', raising=False)
    monkeypatch.delenv('SMZDM_CA_FILE', raising=False)
    with pytest.raises(FileNotFoundError):
        load_config()
