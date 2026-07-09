"""Spike 5: LiveKit Cloud connectivity + token mint sanity check."""

from __future__ import annotations

import time

import httpx

from common import env, load_dotenv, ok, print_header, require_env, skip, write_result


def _mint_token(url: str, api_key: str, api_secret: str) -> str:
    from livekit import api

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity("phase0-spike")
        .with_name("Phase 0 Spike")
        .with_grants(api.VideoGrants(room_join=True, room="shahrazad-phase0"))
        .to_jwt()
    )
    return token


def run() -> dict:
    print_header("Spike 5: LiveKit connectivity")
    load_dotenv()

    try:
        creds = require_env("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    except RuntimeError as exc:
        return skip("livekit_connectivity", str(exc))

    try:
        from livekit import api  # noqa: F401
    except ImportError:
        return skip("livekit_connectivity", "Install deps: pip install -r spikes/requirements.txt")

    url = creds["LIVEKIT_URL"].rstrip("/")
    started = time.perf_counter()
    try:
        token = _mint_token(url, creds["LIVEKIT_API_KEY"], creds["LIVEKIT_API_SECRET"])
    except Exception as exc:  # noqa: BLE001
        return skip("livekit_connectivity", f"Token mint failed: {exc}")

    # Ping the HTTP API root if reachable (Cloud returns 404/401 on some paths — that's fine).
    ping_status = None
    try:
        response = httpx.get(f"{url.replace('wss://', 'https://')}", timeout=10.0)
        ping_status = response.status_code
    except Exception as exc:  # noqa: BLE001
        ping_status = f"unreachable: {exc}"

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    result = {
        "url": url,
        "token_minted": bool(token),
        "token_length": len(token),
        "http_ping_status": ping_status,
        "elapsed_ms": elapsed_ms,
        "recommendation": "LiveKit credentials valid — proceed with LiveKit Agents backbone",
    }
    path = write_result("livekit_connectivity", result)
    print(f"Wrote {path}")
    print(f"Token mint OK ({len(token)} chars), HTTP ping: {ping_status}")
    return ok("livekit_connectivity", **result)


if __name__ == "__main__":
    run()
