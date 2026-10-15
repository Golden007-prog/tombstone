"""A thin provider interface, so the agent loop does not care which model is behind it.

Deliberately minimal: the model's only job in this product is to pick a tool name and fill its
arguments. It never writes Cypher and never phrases the final verdict, so there is no reason to
take on a framework dependency for it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


class Provider:
    """Chat-with-tools against whichever provider has a key in the environment."""

    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = (provider or os.environ.get("LLM_PROVIDER") or self._detect() or "").lower()
        if not self.provider:
            raise LLMError(
                "No LLM key found. Set one of ANTHROPIC_API_KEY / OPENAI_API_KEY / "
                "GEMINI_API_KEY / GROQ_API_KEY in .env (see .env.example)."
            )
        self.model = model or os.environ.get("LLM_MODEL") or self._default_model()

    @staticmethod
    def _detect() -> str | None:
        for env, name in (
            ("ANTHROPIC_API_KEY", "anthropic"),
            ("OPENAI_API_KEY", "openai"),
            ("GEMINI_API_KEY", "gemini"),
            ("GROQ_API_KEY", "groq"),
        ):
            if os.environ.get(env):
                return name
        return None

    def _default_model(self) -> str:
        return {
            "anthropic": "claude-sonnet-5-5",
            "openai": "gpt-5.1",
            "gemini": "gemini-3-pro",
            "groq": "llama-3.3-70b-versatile",
        }[self.provider]

    def _key(self) -> str:
        return os.environ[
            {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "groq": "GROQ_API_KEY",
            }[self.provider]
        ]

    # ---- transport ----
    @staticmethod
    def _post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"{e.code} {e.read()[:400].decode(errors='replace')}") from e

    def choose_tool(self, system: str, question: str, catalogue: dict) -> dict:
        """Return {"tool": name, "args": {...}} -- the model's ONLY decision.

        The response schema has no field for an answer, a verdict or a summary. The model is not
        asked to hedge about what the graph contains; it is structurally unable to say anything
        about it. Everything the user reads is produced by the Cypher in tools.py.
        """
        tool_list = "\n".join(f"- {n}: {d}" for n, d in catalogue.items())
        prompt = (
            f"{system}\n\nAvailable tools:\n{tool_list}\n\n"
            f'User question: "{question}"\n\n'
            "Reply with ONLY a JSON object: "
            '{"tool": "<one tool name from the list>", "args": {<arguments>}}. '
            "No prose, no explanation, no markdown fence."
        )

        if self.provider == "anthropic":
            out = self._post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": self._key(), "anthropic-version": "2023-06-01"},
                {"model": self.model, "max_tokens": 400,
                 "messages": [{"role": "user", "content": prompt}]},
            )
            text = "".join(b.get("text", "") for b in out.get("content", []))
        elif self.provider in ("openai", "groq"):
            base = ("https://api.openai.com/v1" if self.provider == "openai"
                    else "https://api.groq.com/openai/v1")
            out = self._post(
                f"{base}/chat/completions",
                {"authorization": f"Bearer {self._key()}"},
                {"model": self.model, "max_tokens": 400,
                 "messages": [{"role": "user", "content": prompt}]},
            )
            text = out["choices"][0]["message"]["content"]
        elif self.provider == "gemini":
            out = self._post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self._key()}",
                {},
                {"contents": [{"parts": [{"text": prompt}]}]},
            )
            text = out["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise LLMError(f"unsupported provider {self.provider}")

        return self._parse(text)

    @staticmethod
    def _parse(text: str) -> dict:
        t = (text or "").strip()
        if t.startswith("```"):
            t = t.split("```")[1]
            if t.startswith("json"):
                t = t[4:]
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end < 0:
            raise LLMError(f"model did not return JSON: {text[:200]!r}")
        obj = json.loads(t[start : end + 1])
        if "tool" not in obj:
            raise LLMError(f"model response has no 'tool' key: {obj}")
        obj.setdefault("args", {})
        return obj
