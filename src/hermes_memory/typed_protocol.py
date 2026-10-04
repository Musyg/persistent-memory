"""Small stdlib wire helpers; importing them does not open an authority store."""
import json

R3_SHA = "96df9605db923af4ec368ad7d550a02fb9d0c9f270499d6851cb0b727178a5ed"


class ContractError(ValueError):
    def __init__(self, reason, status=400):
        self.reason, self.status = reason, status
        super().__init__(reason)


def require(value, reason, status=400):
    if not value:
        raise ContractError(reason, status)


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate_json_key")
            value[key] = item
        return value
    def invalid_number(_):
        raise ContractError("nonfinite_json_number")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_number)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ContractError("invalid_json") from exc


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
