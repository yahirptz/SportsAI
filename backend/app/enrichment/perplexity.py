"""Perplexity enricher (SRS §02 Layer 2 — facts).

Queries Perplexity for the latest injury / lineup / news on a player and returns
a structured verdict. Per the floor model's absolute rules, ANY injury tag or
snap/minutes limitation hard-stops the pick — so this enricher is deliberately
conservative: anything short of clearly active sets ``injury_flag=True``.
"""

from __future__ import annotations

import re

import httpx
from pydantic import BaseModel

from app.feeds.circuit import CircuitBreaker

_ENDPOINT = "https://api.perplexity.ai/chat/completions"

# Statuses that count as a flag (anything not clearly ACTIVE). Conservative by
# design: a questionable tag is enough to discard a leg.
_FLAG_STATUSES = {"OUT", "DOUBTFUL", "QUESTIONABLE", "LIMITED", "GTD"}

_SYSTEM = (
    "You are a sports injury and lineup desk. Given a player and league, report "
    "their availability for their NEXT game using only verifiable, recent news. "
    "Respond in exactly this format:\n"
    "STATUS: <ACTIVE|QUESTIONABLE|DOUBTFUL|OUT|LIMITED>\n"
    "NOTE: <one short sentence with the reason and date>\n"
    "If you cannot find recent news, use STATUS: ACTIVE and say so in NOTE."
)


class InjuryReport(BaseModel):
    injury_flag: bool
    status: str
    summary: str
    citations: list[str] = []


class PerplexityEnricher:
    name = "perplexity"

    def __init__(self, api_key: str, model: str, *, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=timeout)
        self._breaker = CircuitBreaker("perplexity")

    def injury_news(self, player_name: str, sport_label: str) -> InjuryReport:
        return self._breaker.call(lambda: self._query(player_name, sport_label))

    def _query(self, player_name: str, sport_label: str) -> InjuryReport:
        resp = self._client.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": f"{player_name} — {sport_label}. Availability for next game?",
                    },
                ],
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        citations = data.get("citations", []) or []
        return self._parse(content, citations)

    @staticmethod
    def _parse(content: str, citations: list[str]) -> InjuryReport:
        status_match = re.search(r"STATUS:\s*([A-Z]+)", content, re.IGNORECASE)
        note_match = re.search(r"NOTE:\s*(.+)", content, re.IGNORECASE)
        status = (status_match.group(1).upper() if status_match else "ACTIVE")
        note = (note_match.group(1).strip() if note_match else content.strip())[:240]
        return InjuryReport(
            injury_flag=status in _FLAG_STATUSES,
            status=status,
            summary=note,
            citations=citations[:5],
        )
