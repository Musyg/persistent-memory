"""Explicit admin admission/sync and opt-in entry point for the existing service."""
import argparse
from dataclasses import fields
import json
from pathlib import Path

from hermes_memory.core import Authority, Memory
from .typed_client import token_from_file
from .typed_facade import Facade, Policy, make_server, require, strict_json


def main(argv=None):
    parser = argparse.ArgumentParser()
    for key in ("authority", "anchor", "store", "index", "config"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8079)
    parser.add_argument("--token-file")
    parser.add_argument("operation", choices=("put", "sync", "serve", "context"))
    parser.add_argument("--request")
    args = parser.parse_args(argv)
    config = strict_json(Path(args.config).read_bytes())
    require(type(config) is dict and set(config) <= {field.name for field in fields(Policy)}, "invalid_config")
    policy = Policy(**config)
    authority = Authority.open(args.authority, args.anchor)
    memory = Memory.open(args.store, authority)
    facade = Facade(memory, args.index, policy)
    if args.operation == "serve":
        token = token_from_file(args.token_file) if args.token_file else None
        server = make_server(memory, facade, args.host, args.port, token)
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    if args.operation in {"put", "context"}:
        require(args.request is not None, "request_file_required")
        request = Path(args.request).read_bytes()
        require(len(request) <= 262144, "body_limit", 413)
        payload = strict_json(request)
        result = facade.admit_source(payload) if args.operation == "put" else facade.context(payload)
    else:
        require(args.request is None, "sync_request_not_allowed")
        result = facade.sync({"schema_version": 1, "policy_id": policy.policy_id})
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
