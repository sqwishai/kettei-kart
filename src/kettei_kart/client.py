"""Native decision APIs with bounded retries, pacing and strict response checks."""

import gzip
import hashlib
import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass

import requests

from .actions import OUTCOMES
from .observation import QUESTION, Observation


@dataclass(frozen=True)
class Provider:
    url: str
    model: str
    key_variable: str


PROVIDERS = {
    "sqwish": Provider("https://api.sqwish.ai/v1/decide", "kettei-fat", "SQWISH_API_KEY"),
    "liquid": Provider(
        "https://api.liquid.ai/decisions/v1/systemone", "d1-ultra", "LIQUID_API_KEY"
    ),
    "typesafe": Provider("https://api.typesafe.ai/v1/systemone", "jev-1.14.0", "TYPESAFE_API_KEY"),
}
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504, 520, 522, 524}


class RateLimiter:
    """Share a send budget between both clients in a head-to-head race."""

    def __init__(self, rate: float):
        if not 0 < rate <= 7.5:
            raise ValueError("Rate must be in (0, 7.5]")
        self._lock = threading.Lock()
        self._interval, self._next = 1 / rate, 0.0

    def __call__(self):
        with self._lock:
            time.sleep(max(0, self._next - time.monotonic()))
            self._next = time.monotonic() + self._interval


def validate_probabilities(
    values: dict, *, rounded: bool = False, outcomes: dict = OUTCOMES
) -> dict[str, float]:
    """Accept Jev's hundredth-rounded scores without changing their ranking.

    The original values and sum remain in the receipt. N rounded probabilities
    can accumulate at most N * 0.005 rounding error. Other providers use a tighter
    tolerance. No missing, negative, infinite or extra outcome is accepted.
    """
    if not isinstance(values, dict) or set(values) != set(outcomes):
        raise ValueError("The provider returned different action keys")
    if any(
        isinstance(p, bool)
        or not isinstance(p, (int, float))
        or not math.isfinite(p)
        or not 0 <= p <= 1
        for p in values.values()
    ):
        raise ValueError("The provider returned an invalid probability")
    total = sum(values.values())
    hundredths = all(abs(p * 100 - round(p * 100)) < 1e-7 for p in values.values())
    tolerance = len(values) * 0.005 + 1e-9 if rounded and hundredths else 0.005
    if total <= 0 or abs(total - 1) > tolerance:
        raise ValueError("The provider probabilities do not sum to one")
    return {name: p / total for name, p in values.items()} if rounded else dict(values)


def pack_json(body: dict, *, compress: bool) -> tuple[bytes, dict, dict]:
    plain = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    wire = plain
    headers = {"Content-Type": "application/json"}
    start = time.perf_counter()
    if compress and len(plain) >= 16 * 1024:
        candidate = gzip.compress(plain, compresslevel=1, mtime=0)
        if len(candidate) <= len(plain) * 0.95:
            wire = candidate
            headers["Content-Encoding"] = "gzip"
    return (
        wire,
        headers,
        {
            "plain_bytes": len(plain),
            "wire_bytes": len(wire),
            "compression_ms": (time.perf_counter() - start) * 1000,
            "content_encoding": headers.get("Content-Encoding", "identity"),
        },
    )


class DecisionClient:
    def __init__(self, provider: str = "sqwish", *, rate: float = 1.5, max_attempts: int = 5000):
        if not 0 < rate <= 7.5 or max_attempts < 1:
            raise ValueError("Rate must be in (0, 7.5]; max_attempts must be positive")
        self.provider = provider
        self.config = PROVIDERS[provider]
        self._key = os.environ.get(self.config.key_variable, "").strip()
        if not self._key:
            raise ValueError(f"Set {self.config.key_variable} before starting a run")
        self._session = requests.Session()
        self._last_send = 0.0
        self.rate, self.max_attempts, self.attempts = rate, max_attempts, 0
        self.send_gate = None

    def close(self) -> None:
        self._session.close()

    def redact(self, error: object) -> str:
        """Keep credentials out of caller-owned logs, including exception messages."""
        return str(error).replace(self._key, "[redacted]")

    def _request(
        self, observation: Observation, outcomes: dict = OUTCOMES
    ) -> tuple[dict, dict, dict]:
        headers = {"Authorization": "Bearer " + self._key}
        if self.provider == "sqwish":
            body = {
                "model": self.config.model,
                "context": observation.context,
                "images": observation.images(),
                "fallback": "none",
                "decisions": [
                    {"id": "action", "kind": "single", "question": QUESTION, "outcomes": outcomes}
                ],
            }
        else:
            body = {
                "model": self.config.model,
                "questions": {
                    "action": {"type": "choice", "instructions": QUESTION, "criteria": outcomes}
                },
            }
            if self.provider == "typesafe":
                state, assets, files = observation.context, {}, []
                for i, frame in enumerate(observation.frames, 1):
                    asset, part = str(uuid.uuid4()), f"camera{i}"
                    state = state.replace(f"<image:{i}>", asset)
                    assets[asset] = {"type": "image", "format": "jpeg", "part": part}
                    files.append((part, (part + ".jpg", frame.jpeg, "image/jpeg")))
                body.update(state=state, assets=assets)
                files.insert(0, ("request", (None, json.dumps(body), "application/json")))
                headers["TypeSafe-Danger-Zone-Images"] = "true"
                # Prepare once so even the multipart boundary remains identical on retry.
                prepared = requests.Request("POST", self.config.url, files=files).prepare()
                headers["Content-Type"] = prepared.headers["Content-Type"]
                wire = prepared.body
                return (
                    {"data": wire},
                    headers,
                    {
                        "request_sha256": hashlib.sha256(wire).hexdigest(),
                        "wire_bytes": len(wire),
                        "content_encoding": "multipart",
                    },
                )
            remaining, state = observation.context, []
            for image in observation.images():
                before, anchor, remaining = remaining.partition(f"<image:{image['id']}>")
                if not anchor:
                    raise ValueError("Missing chronological image anchor")
                if before:
                    state.append({"type": "text", "text": before})
                state.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image['media_type']};base64,{image['data']}"},
                    }
                )
            if remaining:
                state.append({"type": "text", "text": remaining})
            body["state"] = state
        wire, content_headers, metadata = pack_json(body, compress=self.provider == "sqwish")
        headers.update(content_headers)
        metadata["request_sha256"] = hashlib.sha256(wire).hexdigest()
        return {"data": wire}, headers, metadata

    def decide(
        self, observation: Observation, outcomes: dict = OUTCOMES
    ) -> tuple[dict[str, float], dict]:
        start = time.perf_counter()
        payload, headers, metadata = self._request(observation, outcomes)
        attempts = []
        for attempt in range(3):
            if self.attempts >= self.max_attempts:
                raise RuntimeError("Request-attempt limit reached")
            time.sleep(max(0, self._last_send + 1 / self.rate - time.monotonic()))
            if self.send_gate is not None:
                self.send_gate()
            self._last_send = time.monotonic()
            self.attempts += 1
            sent = time.perf_counter()
            try:
                response = self._session.post(
                    self.config.url,
                    **payload,
                    headers=headers,
                    timeout=(10, 45),
                    allow_redirects=False,
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                attempts.append(
                    {"error": type(error).__name__, "seconds": time.perf_counter() - sent}
                )
                if attempt == 2:
                    raise RuntimeError("API connection failed after three attempts") from None
                wait = 2**attempt
            else:
                attempts.append(
                    {"status": response.status_code, "seconds": time.perf_counter() - sent}
                )
                if response.status_code == 200:
                    break
                if response.status_code not in TRANSIENT_STATUSES or attempt == 2:
                    # Never include provider error bodies: they may echo a request or key.
                    raise RuntimeError(f"API returned HTTP {response.status_code}")
                retry_after = response.headers.get("Retry-After", "")
                wait = (
                    float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2**attempt
                )
                if wait > 60:
                    raise RuntimeError("Provider requested a retry delay above the 60-second limit")
            time.sleep(wait)
        result = response.json()
        if result.get("model") != self.config.model or result.get("fallback"):
            raise ValueError("The API returned a different model or a fallback")
        answer = result["decisions" if self.provider == "sqwish" else "answers"]["action"]
        raw = answer["probabilities"]
        probabilities = validate_probabilities(
            raw, rounded=self.provider == "typesafe", outcomes=outcomes
        )
        receipt = {
            **metadata,
            "model": result["model"],
            "request_id": result.get("id"),
            "latency_s": time.perf_counter() - start,
            "attempts": attempts,
            "usage": result.get("usage", {}),
            "charge": result.get("charge"),
            "timing_ms": result.get("timing_ms"),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "raw_probabilities": raw,
            "raw_probability_sum": sum(raw.values()),
        }
        return probabilities, receipt
