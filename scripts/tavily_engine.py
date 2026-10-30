"""
scripts/tavily_engine.py
Unified Tavily Grounding Service for Maritime Cargo Surveying & YouTube Media Automation.
Provides real-time fact grounding, vessel verification, metocean weather checks, and media trend retrieval.
"""

import os
import sys
import json
import sqlite3
import hashlib
from typing import Dict, List, Optional, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TAVILY_API_URL = "https://api.tavily.com"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tavily_cache.db")


class TavilyGroundingEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not self.api_key:
            # Fallback to local config file if present
            cfg_path = os.path.join(os.path.dirname(__file__), "..", ".env")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("TAVILY_API_KEY="):
                            self.api_key = line.strip().split("=", 1)[1].strip('"').strip("'")
        self._init_cache()

    def _init_cache(self) -> None:
        """Initializes a local SQLite cache to avoid redundant billable queries."""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    query TEXT,
                    search_depth TEXT,
                    response_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _get_hash(self, query: str, search_depth: str) -> str:
        return hashlib.sha256(f"{query.lower().strip()}:{search_depth}".encode("utf-8")).hexdigest()

    def search(
        self,
        query: str,
        search_depth: str = "basic",
        topic: str = "general",
        days: Optional[int] = None,
        max_results: int = 3,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Executes an agentic search optimized for LLM context windows."""
        q_hash = self._get_hash(query, search_depth)

        if use_cache:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT response_json FROM search_cache WHERE query_hash = ?", (q_hash,)
                ).fetchone()
                if row:
                    return json.loads(row[0])

        if not self.api_key:
            # Return structured stub response when API key is not yet set
            return {
                "status": "mock_response",
                "notice": "TAVILY_API_KEY not configured. Set TAVILY_API_KEY in .env to enable live search.",
                "query": query,
                "answer": f"Simulated grounding answer for query: '{query}'",
                "results": [
                    {
                        "title": f"Grounded Context: {query}",
                        "url": "https://grounding.leewu-ai.internal",
                        "content": f"Verified factual data point corresponding to query '{query}' retrieved via Tavily agentic pipeline."
                    }
                ]
            }

        payload: Dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "topic": topic,
            "max_results": max_results,
            "include_answer": True,
            "include_raw_content": False
        }

        if days:
            payload["days"] = days
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        req = Request(
            f"{TAVILY_API_URL}/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "LeeWu-TavilyEngine/1.0"}
        )

        try:
            with urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode("utf-8"))

                if use_cache:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO search_cache (query_hash, query, search_depth, response_json) VALUES (?, ?, ?, ?)",
                            (q_hash, query, search_depth, json.dumps(data))
                        )
                        conn.commit()

                return data
        except HTTPError as e:
            return {"error": f"Tavily HTTP {e.code}: {e.reason}", "results": []}
        except URLError as e:
            return {"error": f"Tavily Network Error: {e.reason}", "results": []}

    # Specialized Maritime Grounding Methods
    def verify_vessel(self, imo_number: str, vessel_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetches confirmed vessel particulars and classification records."""
        q = f"IMO {imo_number} vessel particulars deadweight beam draft flag class"
        if vessel_name:
            q = f"{vessel_name} {q}"
        return self.search(
            query=q,
            search_depth="advanced",
            include_domains=["vesselfinder.com", "marinetraffic.com", "balticshipping.com"],
            max_results=2
        )

    def get_port_metocean(self, port_name: str, date_str: str) -> Dict[str, Any]:
        """Reconstructs historical meteorological conditions during loading/discharge."""
        q = f"Port of {port_name} weather conditions rainfall wind speed {date_str}"
        return self.search(
            query=q,
            search_depth="advanced",
            include_domains=["wunderground.com", "timeanddate.com", "weather.com"],
            max_results=2
        )

    # Specialized Media Studio Methods
    def fact_check_claim(self, claim_statement: str) -> Dict[str, Any]:
        """Fact-checks a script assertion against authoritative news and docs."""
        return self.search(
            query=f"verify fact: {claim_statement}",
            search_depth="basic",
            max_results=3
        )

    def get_trending_topics(self, category: str = "artificial intelligence") -> Dict[str, Any]:
        """Retrieves breaking developments from the past 48 hours for video planning."""
        return self.search(
            query=f"latest breakthroughs news in {category}",
            topic="news",
            days=2,
            max_results=5
        )


if __name__ == "__main__":
    engine = TavilyGroundingEngine()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "vessel" and len(sys.argv) > 2:
            print(json.dumps(engine.verify_vessel(sys.argv[2]), indent=2))
        elif cmd == "weather" and len(sys.argv) > 3:
            print(json.dumps(engine.get_port_metocean(sys.argv[2], sys.argv[3]), indent=2))
        elif cmd == "fact" and len(sys.argv) > 2:
            print(json.dumps(engine.fact_check_claim(" ".join(sys.argv[2:])), indent=2))
        elif cmd == "trends":
            print(json.dumps(engine.get_trending_topics(), indent=2))
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage: python tavily_engine.py [vessel <IMO>|weather <port> <date>|fact <claim>|trends]")
