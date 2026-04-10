"""X (Twitter) API v2 client — search recent tweets with OAuth 1.0a.

Uses curl via subprocess to avoid adding external dependencies.
Keys are loaded from environment variables (X_API_* in .env).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field

from app.core.logger import logger

# ── Credentials (from env) ─────────────────────────────────

_s = get_settings()
CONSUMER_KEY = os.environ.get("X_API_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("X_API_CONSUMER_SECRET", "")
ACCESS_TOKEN = os.environ.get("X_API_ACCESS_TOKEN", "")
ACCESS_TOKEN_SECRET = os.environ.get("X_API_ACCESS_TOKEN_SECRET", "")


@dataclass
class Tweet:
    """Simplified tweet from search results."""
    id: str
    author_id: str
    author_username: str = ""
    author_name: str = ""
    text: str = ""
    created_at: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    views: int = 0
    url: str = ""
    media: list[str] = field(default_factory=list)


def _oauth1_signature(method: str, url: str, params: dict) -> str:
    """Generate OAuth 1.0a HMAC-SHA1 signature and return Authorization header."""
    base_params = {
        "oauth_consumer_key": CONSUMER_KEY,
        "oauth_nonce": base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest())[:32].hex(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": ACCESS_TOKEN,
        "oauth_version": "1.0",
    }
    base_params.update(params)

    # Build signature base string
    param_str = "&".join(
        f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(base_params.items())
    )
    base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_str, safe='')}"

    signing_key = f"{CONSUMER_SECRET}&{ACCESS_TOKEN_SECRET}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    # Build Authorization header
    auth_params = {k: v for k, v in base_params.items() if k.startswith("oauth_")}
    auth_params["oauth_signature"] = signature

    header_parts = []
    for k in sorted(auth_params.keys()):
        header_parts.append(f'{k}="{urllib.parse.quote(str(auth_params[k]), safe="")}"')
    return "OAuth " + ", ".join(header_parts)


def search_tweets(query: str, max_results: int = 30, sort_order: str = "relevancy") -> list[Tweet]:
    """Search recent tweets (up to 7 days) via X API v2.

    Args:
        query: Search keyword (no 'from:' prefix by default)
        max_results: Max results to collect (paginated, 10 per request)
        sort_order: 'relevancy' or 'recency'
    """
    api_url = "https://api.x.com/2/tweets/search/recent"

    all_tweets: list[Tweet] = []
    next_token = None
    pages = 0
    max_pages = (max_results + 9) // 10  # 10 per page

    while pages < max_pages:
        # Build query params
        params = {
            "query": query,
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics,attachments",
            "expansions": "attachments.media_keys,author_id",
            "media.fields": "url,type",
            "user.fields": "username,name",
            "sort_order": sort_order,
        }
        if next_token:
            params["next_token"] = next_token

        query_string = urllib.parse.urlencode(params, safe="")
        full_url = f"{api_url}?{query_string}"

        auth_header = _oauth1_signature("GET", api_url, params)

        try:
            result = subprocess.run(
                [
                    "curl", "-s", "--max-time", "15", full_url,
                    "-H", f"Authorization: {auth_header}",
                    "-H", "Content-Type: application/json",
                ],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                logger.warning(f"curl failed: {result.stderr[:200]}")
                break

            data = json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"X API request failed: {e}")
            break

        if isinstance(data, dict) and "errors" in data:
            err = data["errors"][0]
            if err.get("code") == 88:
                logger.warning("X API rate limited")
                break
            logger.warning(f"X API error: {err.get('message', err)[:200]}")
            break

        if not isinstance(data, dict) or not data.get("data"):
            break

        # Build lookup maps
        includes = data.get("includes", {})
        users = {u["id"]: u for u in includes.get("users", [])}
        media_map = {m["media_key"]: m for m in includes.get("media", [])}

        for tweet in data["data"]:
            metrics = tweet.get("public_metrics", {})
            author = users.get(tweet.get("author_id"), {})
            media_keys = tweet.get("attachments", {}).get("media_keys", [])
            media_urls = []
            for mk in media_keys:
                m = media_map.get(mk, {})
                if m.get("type") == "photo" and m.get("url"):
                    media_urls.append(m["url"])

            t = Tweet(
                id=tweet["id"],
                author_id=tweet.get("author_id", ""),
                author_username=author.get("username", ""),
                author_name=author.get("name", ""),
                text=tweet.get("text", ""),
                created_at=tweet.get("created_at", ""),
                likes=metrics.get("like_count", 0),
                reposts=metrics.get("retweet_count", 0),
                replies=metrics.get("reply_count", 0),
                views=metrics.get("impression_count", 0),
                url=f"https://x.com/{author.get('username', '')}/status/{tweet['id']}",
                media=media_urls,
            )
            all_tweets.append(t)

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1
        time.sleep(1.5)  # rate limit padding

    logger.info(f"X API search '{query}': {len(all_tweets)} tweets found")
    return all_tweets


def sort_by_engagement(tweets: list[Tweet]) -> list[Tweet]:
    """Sort by engagement: likes + reposts*1.5 + replies*2 + views*0.01."""
    def score(t: Tweet) -> float:
        return t.likes + t.reposts * 1.5 + t.replies * 2 + t.views * 0.01
    return sorted(tweets, key=score, reverse=True)
