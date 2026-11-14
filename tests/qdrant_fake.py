"""Test helpers: an in-process stand-in for the Qdrant REST calls the projection makes, and a
deterministic embedder. The real server is exercised separately in tests_integration/."""
import hashlib
import math
import re
from urllib.parse import urlsplit


class FakeQdrant:
    """Collections, keyword filters, upsert, delete, scroll and cosine query; nothing else."""

    def __init__(self):
        self.collections = {}
        self.down = False
        self.calls = []

    def __call__(self, method, path, body=None, allow_404=False):
        if self.down:
            raise ConnectionRefusedError("qdrant down")
        self.calls.append((method, path))
        parts = urlsplit(path).path.strip("/").split("/")
        assert parts[0] == "collections", path
        name, rest = parts[1], parts[2:]
        if not rest:
            if method == "GET":
                if name not in self.collections:
                    if allow_404:
                        return None
                    raise OSError("404")
                return {"config": {"params": {"vectors": {"size": self.collections[name]["size"]}}}}
            assert method == "PUT" and name not in self.collections
            self.collections[name] = {"size": body["vectors"]["size"], "points": {}}
            return True
        points = self.collections[name]["points"]
        if rest == ["index"]:
            return True
        if rest == ["points"] and method == "PUT":
            for p in body["points"]:
                assert len(p["vector"]) == self.collections[name]["size"]
                points[str(p["id"])] = {"vector": p["vector"], "payload": dict(p["payload"])}
            return True
        if rest == ["points", "delete"]:
            for pid in body["points"]:
                points.pop(str(pid), None)
            return True
        matching = [(pid, p) for pid, p in sorted(points.items()) if self._match(p["payload"], body.get("filter"))]
        if rest == ["points", "scroll"]:
            start = int(body.get("offset") or 0)
            page = matching[start:start + body["limit"]]
            nxt = start + body["limit"] if start + body["limit"] < len(matching) else None
            return {"points": [{"id": pid} for pid, _ in page], "next_page_offset": nxt}
        if rest == ["points", "query"]:
            threshold = body.get("score_threshold", -2.0)
            scored = sorted(((self._cos(body["query"], p["vector"]), pid, p) for pid, p in matching),
                            key=lambda x: (-x[0], x[1]))
            scored = [x for x in scored if x[0] >= threshold][:body["limit"]]
            return {"points": [{"id": pid, "score": s, "payload": p["payload"]} for s, pid, p in scored]}
        raise AssertionError((method, path))

    @staticmethod
    def _match(payload, flt):
        return all(payload.get(c["key"]) == c["match"]["value"] for c in (flt or {}).get("must", []))

    @staticmethod
    def _cos(a, b):
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


class HashEmbedder:
    """Bag of hashed words with a few synonym groups, enough to tell semantic from lexical hits."""

    model_id = "test:hash-embedder"
    SYNONYMS = {"firewall": "parefeu", "pare": "parefeu", "feu": "parefeu", "pare-feu": "parefeu",
                "receiver": "recepteur", "recepteur": "recepteur"}

    def __init__(self, dim=1024):
        self.dim = dim
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        out = []
        for text in texts:
            vector = [0.0] * self.dim
            for word in re.findall(r"\w+", text.casefold()):
                word = self.SYNONYMS.get(word, word)
                vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(vector)
        return out
