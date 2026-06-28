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
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from .config import MultiAgentConfig
from .otel_utils import set_token_cost_attributes as _set_token_cost_attributes
from .prompts import PROMPTS
from .state import ResearchResult, TraceEvent, make_event


# ---------------------------------------------------------------------------
# Default search / fetch implementations
# ---------------------------------------------------------------------------

def _default_web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search via DuckDuckGo Instant Answer API (no key required).

    Falls back to Tavily when TAVILY_API_KEY is set in the environment.
    Returns at most *max_results* items, each with 'title', 'url', 'snippet'.
    """
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

    # DuckDuckGo fallback via ddgs (package renamed from duckduckgo_search to ddgs)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
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

    SYSTEM_PROMPT = PROMPTS.researcher_system

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
            self.model = ChatOpenAI(
                model=self.config.researcher_model,
                temperature=self.config.temperature,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _gather_context(self, query: str) -> tuple[list[dict], list[TraceEvent]]:
        """Run web_search then fetch all pages concurrently, preserving result order."""
        events: list[TraceEvent] = []
        results = self.search_fn(query, self.config.max_search_results)
        events.append(make_event("researcher","tool_call", {"tool": "web_search", "query": query, "n_results": len(results)}))

        urls = [r.get("url", "") for r in results]
        workers = max(1, sum(1 for u in urls if u))

        def _fetch(url: str) -> str:
            return self.fetch_fn(url, self.config.max_page_chars) if url else ""

        with ThreadPoolExecutor(max_workers=workers) as pool:
            page_texts = list(pool.map(_fetch, urls))

        enriched: list[dict] = []
        for r, url, page_text in zip(results, urls, page_texts):
            if url:
                events.append(make_event("researcher","tool_call", {"tool": "fetch_page", "url": url}))
                enriched.append({**r, "page_text": page_text})
            else:
                enriched.append(r)

        return enriched, events

    def _summarise(self, query: str, context: list[dict], callback=None, runnable_config=None) -> tuple[str, list[TraceEvent]]:
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
        if callback is not None:
            invoke_config = RunnableConfig(callbacks=[callback])
        elif runnable_config is not None:
            invoke_config = runnable_config
        else:
            invoke_config = None
        response = self.model.invoke(messages, **({"config": invoke_config} if invoke_config else {}))
        raw = getattr(response, "content", str(response))
        usage = getattr(response, "usage_metadata", None)
        token_payload: dict = {"model": self.config.researcher_model, "chars": len(raw)}
        if usage:
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            cost = (
                input_t * self.config.input_token_price_per_million / 1_000_000
                + output_t * self.config.output_token_price_per_million / 1_000_000
            )
            token_payload.update({"input_tokens": input_t, "output_tokens": output_t, "cost_usd": cost})
            _set_token_cost_attributes(input_t, output_t, cost)
        events.append(make_event("researcher","llm_response", token_payload))
        return raw, events

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, query: str, callback=None, runnable_config=None) -> tuple[ResearchResult, list[TraceEvent]]:
        """Research *query* and return a :class:`ResearchResult` plus trace events.

        The LLM response is expected to be JSON.  If parsing fails the raw
        text is returned as the summary with an empty sources list.
        """
        all_events: list[TraceEvent] = []

        context, search_events = self._gather_context(query)
        all_events.extend(search_events)

        raw, llm_events = self._summarise(query, context, callback=callback, runnable_config=runnable_config)
        all_events.extend(llm_events)

        # Parse JSON response
        try:
            # Strip markdown code fences if present
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            parsed = json.loads(cleaned)
            result: ResearchResult = {
                "summary": parsed.get("summary", raw),
                "sources": parsed.get("sources", []),
            }
        except (json.JSONDecodeError, ValueError):
            result = {"summary": raw, "sources": []}

        return result, all_events
