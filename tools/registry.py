"""Tool registry. Tools are declared in tools.yaml, and each is either a Python function or an MCP server tool."""
import asyncio, importlib, re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

META = re.compile(r"^\[meta\]\s*(\{.*?\})\s*(?:\n|$)", re.S)
TIMEOUT_S = 40


@dataclass
class Context:
    """What a tool can see of the session."""
    registry: "Registry"
    http: object
    user_text: str = ""
    items: list = field(default_factory=list)   # the numbered list most recently offered to the learner
    subject: object = None                      # the material currently being discussed
    skill: str = "conversation"


def resolve(ref):
    module, name = ref.split(":")
    return getattr(importlib.import_module(module), name)


class Registry:
    def __init__(self, path):
        cfg = yaml.safe_load(Path(path).read_text())
        self.servers = cfg.get("servers", {})
        self.tools = cfg["tools"]

    def schemas(self, names):
        return [{"type": "function", "function": {"name": n, "description": self.tools[n]["description"], "parameters": self.tools[n]["parameters"]}} for n in names if n in self.tools]

    async def mcp_call(self, server, tool, args):
        """Open the MCP server for one call. Tools are used rarely, so a long-lived connection isn't worth managing."""
        cfg = self.servers[server]
        params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
        text = "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")
        if res.is_error:
            raise RuntimeError(text[:300])
        return text

    async def call(self, name, args, ctx):
        if name not in self.tools:
            return f"Unknown tool {name}."
        t = self.tools[name]
        try:
            return await asyncio.wait_for(self._run(t, args, ctx), TIMEOUT_S)
        except asyncio.TimeoutError:
            return "The tool took too long. Tell the learner it didn't work and offer to try again."
        except Exception as e:
            return f"The tool failed ({type(e).__name__}). Tell the learner it didn't work and offer to try again."

    async def _run(self, t, args, ctx):
        if t["provider"] == "python":
            return await resolve(t["function"])(args, ctx)
        text = await self.mcp_call(t["server"], t["tool"], {**args, **t.get("fixed", {})})
        return await resolve(t["after"])(text, ctx) if t.get("after") else text[:t.get("max_chars", 6000)]
