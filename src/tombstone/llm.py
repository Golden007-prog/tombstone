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
        """Turn a model's reply into {"tool": str, "args": dict}, or refuse clearly.

        Models do not reliably obey "no prose, no markdown fence", so this is written for what
        they actually send. Three cases were found by probing it rather than by reasoning:

        * prose containing braces -- "I think {this} is right: {...}" -- made the old
          first-brace-to-last-brace slice produce invalid JSON and raise a raw JSONDecodeError
          out of the provider, rather than the LLMError the caller handles;
        * `args` arriving as a STRING ("path=foo") passed straight through to the dispatcher,
          which calls .get() on it;
        * `tool` arriving as a LIST passed through to be compared against tool names.

        The last two never reach a query -- the dispatcher refuses an unknown tool -- but they
        surface as an internal error instead of as the clear refusal the product promises.
        """
        t = (text or "").strip()
        if t.startswith("```"):
            parts = t.split("```")
            t = parts[1] if len(parts) > 1 else t
            if t.startswith("json"):
                t = t[4:]

        # Try every `{` from the left; the first one that yields a dict with a tool wins. A single
        # first-brace-to-last-brace slice breaks on any prose that happens to contain a brace.
        obj = None
        for start in (i for i, c in enumerate(t) if c == "{"):
            try:
                candidate = json.loads(t[start:t.rfind("}") + 1])
            except Exception:
                continue
            if isinstance(candidate, dict) and "tool" in candidate:
                obj = candidate
                break
        if obj is None:
            raise LLMError(f"model did not return a JSON object with a tool: {text[:200]!r}")

        tool = obj.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            raise LLMError(f"model gave a tool name that is not a string: {tool!r}")
        args = obj.get("args")
        if not isinstance(args, dict):
            # Not an error worth refusing over: every tool either has defaults or says what it
            # needs. Dropping a malformed args object is better than handing it to the dispatcher.
            args = {}
        return {"tool": tool.strip(), "args": args}
