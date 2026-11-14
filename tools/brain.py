"""Every request to the brain: Gemma 4 in llama-server, or the same model in the cloud (tools/providers.py).

llama-server keeps two slots, each with its own cache: DISCUSSION holds the conversation, so each turn only reads the
new words; SIDE takes short requests (vowelling, checks, titles), so they don't push the conversation out of the cache.
"""
import json

from . import providers

SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}   # Google's recommended values for Gemma 4
EXACT = {"temperature": 0}                                     # for vowelling, checks and other answers with one right result
DISCUSSION, SIDE = 0, 1
URL = providers.LLM_URL   # an eval can point this at another OpenAI-style endpoint


def body(messages, max_tokens, slot=SIDE, sampling=EXACT, schema=None, **extra):
    """A chat request. `messages` may be one prompt string. Thinking stays off: the tutor answers straight away."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    b = {"messages": messages, "max_tokens": max_tokens, "id_slot": slot, "chat_template_kwargs": {"enable_thinking": False}, **sampling, **extra}
    if schema:
        b["response_format"] = {"type": "json_schema", "json_schema": {"schema": schema}}
    return providers.llm_body(b)


async def ask(http, messages, max_tokens, timeout=60, **kw):
    """The whole answer as text."""
    r = await http.post(URL, json=body(messages, max_tokens, **kw), headers=providers.LLM_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


async def ask_json(http, messages, max_tokens, schema, timeout=60, **kw):
    """A structured answer with the schema's required keys, tried twice: a cloud provider occasionally returns broken JSON."""
    for attempt in (1, 2):
        try:
            data = json.loads(await ask(http, messages, max_tokens, timeout, schema=schema, **kw))
            if isinstance(data, dict) and all(k in data for k in schema.get("required", ())):
                return data
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
    raise ValueError("the brain returned no valid JSON twice")


async def turn(http, messages, tools, on_text, max_tokens=300):
    """One turn of the discussion, streamed: on_text gets the text so far. Returns the text and any tool calls."""
    b = body(messages, max_tokens, DISCUSSION, SAMPLING, stream=True, **({"tools": tools} if tools else {}))
    text, calls = "", {}
    async with http.stream("POST", URL, json=b, headers=providers.LLM_HEADERS, timeout=120) as r:
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            d = json.loads(line[6:])
            if not d.get("choices"):
                continue
            delta = d["choices"][0].get("delta", {})
            if delta.get("content"):
                text += delta["content"]
                await on_text(text)
            for c in delta.get("tool_calls") or []:
                cur = calls.setdefault(c.get("index", 0), {"id": c.get("id") or f"call_{c.get('index', 0)}", "name": "", "args": ""})
                f = c.get("function") or {}
                cur["name"] += f.get("name") or ""
                cur["args"] += f.get("arguments") or ""
    return text, [calls[i] for i in sorted(calls)]


async def warm(http, messages, slot, **extra):
    """Read a prompt into a local slot's cache ahead of time. Nothing to do in the cloud."""
    if providers.BRAIN == "local":
        await http.post(URL, json=body(messages, 1, slot, **extra), timeout=60)
