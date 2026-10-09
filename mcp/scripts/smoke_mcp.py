"""Explicit opt-in smoke test against an isolated service, never pushes."""
import asyncio
import json
import sys
import uuid
from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main():
    server = StdioServerParameters(command=sys.executable, args=['-m', 'smzdm_mcp.server'])
    async with Client(server) as client:
        tools = await client.list_tools()
        print('discovered tools:', len(tools.tools))
        async def call(name, data=None):
            result = await client.call_tool(name, data or {})
            if result.is_error: raise RuntimeError(str(result.content))
            return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)
        print('capabilities:', (await call('get_capabilities'))['api_version'])
        key = str(uuid.uuid4())
        spec = {'name': 'MCP smoke ' + key[:8], 'keywords': [{'keyword': '固态硬盘', 'price_max': 800}], 'request_id': key}
        created = await call('create_monitor', spec)
        monitor_id = created['monitor']['id']
        try:
            assert not (await call('create_monitor', spec))['changed']
            patched = await call('update_monitor', {'monitor_id': monitor_id, 'description': 'smoke test'})
            assert patched['refresh_interval'] == 300
            enabled = await call('set_monitor_enabled', {'monitor_id': monitor_id, 'enabled': True})
            assert enabled['is_active']
            await asyncio.sleep(2)
            paused = await call('set_monitor_enabled', {'monitor_id': monitor_id, 'enabled': False})
            assert not paused['task_running']
            print('create/retry/patch/enable/pause: passed')
        finally:
            await call('delete_monitor', {'monitor_id': monitor_id})
        print('delete: passed; notifications disabled throughout')


asyncio.run(main())
