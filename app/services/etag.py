import base64
import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    # Equivalent of json-stable-stringify: sorted keys, no whitespace
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_etag_from_json(obj: Any) -> str:
    digest = hashlib.sha256(canonical_json(obj).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
