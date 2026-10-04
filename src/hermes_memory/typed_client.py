"""Read-only bounded typed-memory transport; no redirects, proxies or retries."""
import ipaddress
import http.client
import os
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request

from .typed_protocol import ContractError, R3_SHA, canonical, require, strict_json
from .typed_memory import metadata, RetrievalError


def token_from_file(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) in {0o400, 0o600} and info.st_uid == os.getuid() and info.st_nlink == 1, "private_token_file_required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        actual = os.fstat(descriptor)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns), "token_file_changed")
        require(32 <= actual.st_size <= 4096, "invalid_token_size")
        raw = os.read(descriptor, 4097)
        require(len(raw) == actual.st_size, "token_file_changed")
        token = raw.decode("utf-8").strip()
        require(32 <= len(token) <= 4096 and all(33 <= ord(c) <= 126 for c in token), "invalid_token")
        return token
    finally:
        os.close(descriptor)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, base_url, token_file, policy_id, workspace, timeout=3):
        url = urllib.parse.urlsplit(base_url)
        require(url.scheme in {"http", "https"} and url.hostname and not url.username and not url.password and url.path in {"", "/"} and not url.query and not url.fragment, "invalid_endpoint")
        if url.scheme == "http":
            try:
                address = ipaddress.ip_address(url.hostname)
            except ValueError as exc:
                raise ContractError("http_numeric_private_endpoint_required") from exc
            require(address.is_loopback or address in ipaddress.ip_network("100.64.0.0/10"), "http_private_endpoint_required")
        require(type(timeout) in {int, float} and 0 < timeout <= 5, "invalid_timeout")
        self.base_url, self.token_file = base_url.rstrip("/"), token_file
        self.policy_id, self.workspace, self.timeout = policy_id, workspace, timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def context(self, arguments):
        require(type(arguments) is dict and set(arguments) <= {"query", "as_of", "conditions", "evidence_kinds", "top_k", "max_context_chars"}, "invalid_tool_arguments")
        payload = {"schema_version": 1, "policy_id": self.policy_id, **arguments}
        raw = canonical(payload).encode("utf-8")
        require(len(raw) <= 16384, "request_limit")
        request = urllib.request.Request(self.base_url + "/typed/v1/context", data=raw, method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + token_from_file(self.token_file)})
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                declared = response.headers.get("Content-Length")
                require(declared is None or declared.isdigit(), "invalid_response_length")
                require(declared is None or int(declared) <= 262144, "response_limit")
                raw = response.read(262145)
                if declared is not None and len(raw) < int(declared):
                    raise http.client.IncompleteRead(raw)
                status = response.code
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
            return {"status": "unavailable", "reason": "transport_unavailable", "items": [], "context": "", "context_empty": True}
        require(len(raw) <= 262144, "response_limit")
        result = strict_json(raw)
        require(type(result) is dict and result.get("status") in {"completed", "unavailable", "index_stale", "epoch_changed", "refused", "error"}, "invalid_response")
        if result["status"] != "completed":
            require(status != 200, "status_binding_mismatch")
            require(not result.get("items") and not result.get("context"), "failure_content_forbidden")
            require(set(result) <= {"status", "reason", "items", "context", "context_empty", "complete", "schema_version", "policy_id", "library_sha256"}, "failure_response_fields")
            require(type(result.get("reason")) is str and 0 < len(result["reason"]) <= 256, "invalid_failure_reason")
            return {"status": result["status"], "reason": result.get("reason", "remote_refusal"), "items": [], "context": "", "context_empty": True}
        fields = {"status", "reason", "epoch", "items", "context", "context_empty", "context_chars", "exclusions", "coverage", "complete", "completeness_scope", "backend", "historical_version_access", "confidence_policy", "budget_unit", "schema_version", "policy_id", "library_sha256"}
        require(set(result) == fields, "completed_response_fields")
        require(status == 200 and result.get("schema_version") == 1 and type(result.get("schema_version")) is int and result.get("policy_id") == self.policy_id and result.get("library_sha256") == R3_SHA, "response_binding_mismatch")
        require(type(result["epoch"]) is int and result["epoch"] >= 0 and result["reason"] is None, "invalid_response_epoch")
        constants = {"completeness_scope": "indexed_managed_candidates_at_current_epoch_not_all_results_or_history", "backend": "sqlite_fts5+exact_identifier", "historical_version_access": "unsupported", "confidence_policy": "declared_not_ranked", "budget_unit": "python_characters"}
        require(all(result[key] == value for key, value in constants.items()), "response_semantics_mismatch")
        coverage = result["coverage"]
        require(type(coverage) is dict and set(coverage) == {"unmanaged", "excluded_at_sync", "candidate_limit", "candidate_truncated", "candidate_count"}, "invalid_coverage")
        require(all(type(coverage[key]) is int and coverage[key] >= 0 for key in ("unmanaged", "excluded_at_sync", "candidate_limit", "candidate_count")), "invalid_coverage_count")
        require(1 <= coverage["candidate_limit"] <= 128 and coverage["candidate_count"] <= coverage["candidate_limit"] and type(coverage["candidate_truncated"]) is bool, "invalid_coverage_bound")
        require(type(result["complete"]) is bool and result["complete"] == (not coverage["candidate_truncated"] and coverage["unmanaged"] == 0), "invalid_completeness")
        def validate_ref(ref):
            require(type(ref) is dict and set(ref) == {"workspace", "artifact_id", "version_id"} and all(type(value) is str and 0 < len(value.encode("utf-8")) <= 512 for value in ref.values()) and ref["workspace"] == self.workspace, "response_ref_scope")
        exclusions = result["exclusions"]
        require(type(exclusions) is list and len(exclusions) <= coverage["candidate_count"], "invalid_exclusions")
        for exclusion in exclusions:
            require(type(exclusion) is dict and set(exclusion) == {"ref", "reason"} and type(exclusion["reason"]) is str and 0 < len(exclusion["reason"]) <= 128, "invalid_exclusion")
            validate_ref(exclusion["ref"])
        items = result.get("items")
        require(type(items) is list and len(items) <= arguments.get("top_k", 5), "invalid_items")
        for item in items:
            require(type(item) is dict and set(item) == {"ref", "text", "metadata"} and type(item["text"]) is str, "invalid_item")
            ref = item["ref"]
            validate_ref(ref)
            try:
                normalized = metadata(item["metadata"])
            except RetrievalError as exc:
                raise ContractError("response_metadata_invalid") from exc
            require(normalized == item["metadata"], "response_metadata_noncanonical")
        context = "\n\n".join(item["text"] for item in items)
        require(result.get("context") == context and type(result.get("context_chars")) is int and result["context_chars"] == len(context) and len(context) <= arguments.get("max_context_chars", 2000), "response_context_binding")
        require(type(result.get("context_empty")) is bool and result["context_empty"] == (not context), "response_empty_binding")
        return result
