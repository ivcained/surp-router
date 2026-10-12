#!/usr/bin/env python3
"""Command-line client for surp.ivc.lol.

Stdlib only (Python 3.9+): argparse + urllib. Every command maps 1:1 onto a
public gateway endpoint so agents and scripts can drive Surp without
building API integrations from scratch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

DEFAULT_BASE_URL = "https://surp.ivc.lol"
_TIMEOUT = 120


class SurpError(Exception):
    """API error with the upstream status and body attached."""


def _request(base_url: str, method: str, path: str, payload: dict | None = None,
             api_key: str | None = None, query: dict | None = None) -> tuple[int, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise SurpError(f"cannot reach {url}: {e.reason}") from e


def _print(status: int, body: str, raw: bool) -> int:
    if raw:
        print(body)
    elif status != 200:
        print(body, file=sys.stderr)
    return 0 if status == 200 else 1


def _extract_content(body: str) -> str:
    try:
        doc = json.loads(body)
    except json.JSONDecodeError:
        return body
    try:
        return doc["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return body


def cmd_models(args: argparse.Namespace) -> int:
    status, body = _request(args.base_url, "GET", "/v1/models")
    return _print(status, body, args.json)


def cmd_prices(args: argparse.Namespace) -> int:
    query = {"search": args.query} if args.query else None
    status, body = _request(args.base_url, "GET", "/api/price-compare", query=query)
    return _print(status, body, args.json)


def cmd_status(args: argparse.Namespace) -> int:
    status, body = _request(args.base_url, "GET", "/api/health")
    return _print(status, body, args.json)


def cmd_key_free(args: argparse.Namespace) -> int:
    payload = {"label": args.label, "elevated_requests": args.requests, "elevated_tokens": args.tokens}
    status, body = _request(args.base_url, "POST", "/api/free-key", payload=payload)
    return _print(status, body, args.json)


def cmd_balance(args: argparse.Namespace) -> int:
    status, body = _request(args.base_url, "GET", "/api/keys/balance", query={"key": args.key})
    return _print(status, body, args.json)


def cmd_chat(args: argparse.Namespace) -> int:
    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("error: no prompt given (use -p or pipe stdin)", file=sys.stderr)
        return 2
    messages = ([{"role": "system", "content": args.system}] if args.system else [])
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": args.model,
        "messages": messages,
        "max_tokens": args.max_tokens,
    }
    api_key = args.key or os.environ.get("SURP_API_KEY")
    status, body = _request(args.base_url, "POST", "/v1/chat/completions", payload=payload, api_key=api_key)
    if status == 200 and not args.json:
        print(_extract_content(body))
        return 0
    return _print(status, body, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="surp",
        description="CLI for surp.ivc.lol — OpenAI-compatible AI inference with live cheapest-model routing.",
    )
    parser.add_argument("--version", action="version", version=f"surp-cli {__version__}")
    parser.add_argument("--base-url", default=os.environ.get("SURP_BASE_URL", DEFAULT_BASE_URL),
                        help="gateway base URL (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    # same flags usable after the subcommand for ergonomics
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("models", parents=[common],
                   help="list available routes and models (GET /v1/models)").set_defaults(func=cmd_models)

    p = sub.add_parser("prices", parents=[common], help="compare live Surp prices (GET /api/price-compare)")
    p.add_argument("--query", default="", help="optional model or route search text")
    p.set_defaults(func=cmd_prices)

    sub.add_parser("status", parents=[common],
                   help="gateway and upstream health (GET /api/health)").set_defaults(func=cmd_status)

    p = sub.add_parser("key", parents=[common], help="manage API keys")
    key_sub = p.add_subparsers(dest="key_command", required=True)
    pf = key_sub.add_parser("free", parents=[common], help="create a self-serve free-tier key (POST /api/free-key)")
    pf.add_argument("--label", default="surp-cli")
    pf.add_argument("--requests", type=int, default=1000, help="elevated request budget (max 10000)")
    pf.add_argument("--tokens", type=int, default=200000, help="elevated token budget (max 2000000)")
    pf.set_defaults(func=cmd_key_free)

    p = sub.add_parser("balance", help="check a prepaid key's balance (GET /api/keys/balance)")
    p.add_argument("--key", required=True, help="sk-surp-... prepaid API key")
    p.set_defaults(func=cmd_balance)

    p = sub.add_parser("chat", help="chat completion (POST /v1/chat/completions)")
    p.add_argument("-m", "--model", default="surp/free", help="route to call (default: surp/free)")
    p.add_argument("-p", "--prompt", default="", help="user prompt; reads stdin when omitted and piped")
    p.add_argument("--system", default="", help="optional system message")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--key", default="", help="prepaid API key (or set SURP_API_KEY)")
    p.set_defaults(func=cmd_chat)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SurpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
