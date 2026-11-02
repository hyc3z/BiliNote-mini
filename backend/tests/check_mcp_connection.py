"""Protocol smoke test; read-only tools only, no paid API or video processing."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root=Path(__file__).resolve().parents[1]
    parameters=StdioServerParameters(command=sys.executable,args=[str(root/'mcp_server.py')],env={**os.environ,'PYTHONUTF8':'1'})
    async with stdio_client(parameters) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            tools=await session.list_tools()
            print('MCP handshake OK; tools:',','.join(t.name for t in tools.tools),flush=True)
            result=await session.call_tool('search_notes',{'query':'极客湾'})
            assert not result.isError
            content=result.structuredContent
            if not content:
                content=json.loads(result.content[0].text)
            notes=content['notes'];print('Local note search:',len(notes),'results',flush=True)
            if notes:
                note=await session.call_tool('read_note',{'task_id':notes[0]['task_id'],'limit':500})
                assert not note.isError
                print('Saved summary read OK',flush=True)

if __name__=='__main__':asyncio.run(main())
