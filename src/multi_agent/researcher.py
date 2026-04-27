"""ResearcherAgent — executes web searches and document retrieval.

The agent runs a minimal ReAct loop:
  1. LLM decides which queries to search.
  2. web_search fetches top results.
  3. fetch_page retrieves and truncates page text.
  4. LLM summarises the collected evidence with inline citations.

All three functions (search_fn, fetch_fn, llm) are injectable so tests can
run without network access or real API keys.

Output schema::

    {
        "summary": str,
        "sources": [{"url": str, "excerpt": str}]
    }
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .config import MultiAgentConfig
from .state import ResearchResult, TraceEvent

load_dotenv()


# ---------------------------------------------------------------------------
# Default search / fetch implementations
# ---------------------------------------------------------------------------

def _default_web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search via DuckDuckGo Instant Answer API (no key required).

    Falls back to Tavily when TAVILY_API_KEY is set in the environment.
    Returns at most *max_results* items, each with 'title', 'url', 'snippet'.
    """
    import os
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            resp = client.search(query, max_results=max_results)
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in resp.get("results", [])[:max_results]
            ]
        except Exception:
            pass

    # DuckDuckGo fallback via ddgs
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in results
        ]
    except Exception:
        return []


def _default_fetch_page(url: str, max_chars: int = 1_500) -> str:
    """Fetch a URL and return up to *max_chars* of cleaned plain text."""
    try:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
        resp.raise_for_status()
        text = resp.text
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        return f"[fetch error: {exc}]"


# ---------------------------------------------------------------------------
# ResearcherAgent
# ---------------------------------------------------------------------------

class ResearcherAgent:
    """Runs a search-and-summarise loop for a research query.

    Parameters
    ----------
    model:
        A LangChain-compatible chat model.  When None, a ``ChatOpenAI``
        instance is created from ``config.researcher_model``.
    search_fn:
        ``(query: str, max_results: int) -> list[dict]``.
        Defaults to :func:`_default_web_search`.
    fetch_fn:
        ``(url: str, max_chars: int) -> str``.
        Defaults to :func:`_default_fetch_page`.
    config:
        Shared ``MultiAgentConfig``.
    """

    SYSTEM_PROMPT = (
        "You are a research assistant. Given a query, produce a concise, "
        "well-cited summary. Base every claim strictly on the source material "
        "provided. Return your answer as JSON with keys 'summary' and 'sources'. "
        "'sources' must be a list of objects with 'url' and 'excerpt' keys."
    )

    def __init__(
        self,
        model=None,
        search_fn: Optional[Callable] = None,
        fetch_fn: Optional[Callable] = None,
        config: Optional[MultiAgentConfig] = None,
    ):
        self.config = config or MultiAgentConfig()
        self.search_fn = search_fn or _default_web_search
        self.fetch_fn = fetch_fn or _default_fetch_page

        if model is not None:
            self.model: Any = model
        else:
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(
                model=self.config.researcher_model,
                temperature=self.config.temperature,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _event(self, event_type: str, payload: dict) -> TraceEvent:
        return TraceEvent(
            timestamp=self._ts(),
            agent="researcher",
            event_type=event_type,
            payload=payload,
        )

    def _gather_context(self, query: str) -> tuple[list[dict], list[TraceEvent]]:
        """Run web_search + fetch_page and return raw results + trace events."""
        events: list[TraceEvent] = []
        results = self.search_fn(query, self.config.max_search_results)
        events.append(self._event("tool_call", {"tool": "web_search", "query": query, "n_results": len(results)}))

        enriched: list[dict] = []
        for r in results:
            url = r.get("url", "")
            if not url:
                enriched.append(r)
                continue
            page_text = self.fetch_fn(url, self.config.max_page_chars)
            events.append(self._event("tool_call", {"tool": "fetch_page", "url": url}))
            enriched.append({**r, "page_text": page_text})

        return enriched, events

    def _summarise(self, query: str, context: list[dict], callback=None) -> tuple[str, list[TraceEvent]]:
        """Call the LLM to produce a cited summary from *context*."""
        events: list[TraceEvent] = []
        context_text = "\n\n".join(
            f"[{i+1}] {r.get('url', '')}\n{r.get('page_text') or r.get('snippet', '')}"
            for i, r in enumerate(context)
        )
        messages: list[BaseMessage] = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\n\nSources:\n{context_text}"),
        ]
        invoke_kwargs: dict = {}
        if callback is not None:
            from langchain_core.runnables import RunnableConfig
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])
        response = self.model.invoke(messages, **invoke_kwargs)
        raw = getattr(response, "content", str(response))
        events.append(self._event("llm_response", {"model": self.config.researcher_model, "chars": len(raw)}))
        return raw, events

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, query: str, callback=None) -> tuple[ResearchResult, list[TraceEvent]]:
        """Research *query* and return a :class:`ResearchResult` plus trace events.

        The LLM response is expected to be JSON.  If parsing fails the raw
        text is returned as the summary with an empty sources list.
        """
        all_events: list[TraceEvent] = []

        context, search_events = self._gather_context(query)
        all_events.extend(search_events)

        raw, llm_events = self._summarise(query, context, callback=callback)
        all_events.extend(llm_events)

        # Parse JSON response
        try:
            # Strip markdown code fences if present
            cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
            parsed = json.loads(cleaned)
            result: ResearchResult = {
                "summary": parsed.get("summary", raw),
                "sources": parsed.get("sources", []),
            }
        except (json.JSONDecodeError, ValueError):
            result = {"summary": raw, "sources": []}

        return result, all_events
