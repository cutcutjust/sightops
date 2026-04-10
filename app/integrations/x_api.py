"""X (Twitter) API v2 client — search tweets, fetch replies.

Authentication:
  - Bearer Token (App-Only): for read-only endpoints (search, fetch replies)
  - OAuth 1.0a: for user-context endpoints (post, like, follow, etc.)

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

CONSUMER_KEY = os.environ.get("X_API_CONSUMER_KEY", "")
CONSUMER_SECRET = os.environ.get("X_API_CONSUMER_SECRET", "")
ACCESS_TOKEN = os.environ.get("X_API_ACCESS_TOKEN", "")
ACCESS_TOKEN_SECRET = os.environ.get("X_API_ACCESS_TOKEN_SECRET", "")
BEARER_TOKEN = os.environ.get("X_API_BEARER_TOKEN", "")


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
    engagement_score: float = 0.0

    def compute_score(self) -> float:
        """Weight: likes + reposts*1.5 + replies*2 + views*0.01"""
        self.engagement_score = self.likes + self.reposts * 1.5 + self.replies * 2 + self.views * 0.01
        return self.engagement_score


@dataclass
class TweetComment:
    """A reply/comment to a tweet."""
    id: str
    author_username: str = ""
    author_name: str = ""
    text: str = ""
    created_at: str = ""
    likes: int = 0
    replies: int = 0
    views: int = 0
    url: str = ""
    engagement_score: float = 0.0

    def compute_score(self) -> float:
        """Weight: likes*2 + replies*3 + views*0.005"""
        self.engagement_score = self.likes * 2 + self.replies * 3 + self.views * 0.005
        return self.engagement_score


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

    param_str = "&".join(
        f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(base_params.items())
    )
    base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_str, safe='')}"

    signing_key = f"{CONSUMER_SECRET}&{ACCESS_TOKEN_SECRET}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    auth_params = {k: v for k, v in base_params.items() if k.startswith("oauth_")}
    auth_params["oauth_signature"] = signature

    header_parts = []
    for k in sorted(auth_params.keys()):
        header_parts.append(f'{k}="{urllib.parse.quote(str(auth_params[k]), safe="")}"')
    return "OAuth " + ", ".join(header_parts)


def _make_request(url: str, params: dict, use_bearer: bool = True) -> dict | None:
    """Make an authenticated GET request to X API v2.

    Prefers Bearer Token (App-Only) for read endpoints; falls back to OAuth 1.0a.
    """
    query_string = urllib.parse.urlencode(params, safe="")
    full_url = f"{url}?{query_string}"

    if use_bearer and BEARER_TOKEN:
        auth_header = f"Bearer {BEARER_TOKEN}"
    else:
        auth_header = _oauth1_signature("GET", url, params)

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
            return None

        data = json.loads(result.stdout)

        if isinstance(data, dict) and "errors" in data:
            err = data["errors"][0]
            if err.get("code") == 88:
                logger.warning("X API rate limited")
            elif err.get("code") == 401 or "Unauthorized" in str(err.get("title", "")):
                # Bearer failed, retry with OAuth 1.0a
                if use_bearer and BEARER_TOKEN:
                    logger.info("Bearer Token failed, retrying with OAuth 1.0a")
                    return _make_request(url, params, use_bearer=False)
                logger.warning("X API unauthorized")
            else:
                logger.warning(f"X API error: {err.get('message', str(err))[:200]}")
            return None

        # Also handle top-level 401 (e.g. {"title": "Unauthorized", ...})
        if isinstance(data, dict) and data.get("status") == 401:
            if use_bearer and BEARER_TOKEN:
                logger.info("Bearer Token failed, retrying with OAuth 1.0a")
                return _make_request(url, params, use_bearer=False)
            logger.warning("X API unauthorized")
            return None

        return data
    except Exception as e:
        logger.warning(f"X API request failed: {e}")
        return None


def search_tweets(query: str, max_results: int = 30, sort_order: str = "relevancy") -> list[Tweet]:
    """Search recent tweets (up to 7 days).

    Args:
        query: Search keyword (no 'from:' prefix by default)
        max_results: Max results to collect (paginated, 10 per request)
        sort_order: 'relevancy' or 'recency'
    """
    api_url = "https://api.x.com/2/tweets/search/recent"

    all_tweets: list[Tweet] = []
    next_token = None
    pages = 0
    max_pages = (max_results + 9) // 10

    while pages < max_pages:
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

        data = _make_request(api_url, params)
        if not data or not data.get("data"):
            break

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
            t.compute_score()
            all_tweets.append(t)

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1
        time.sleep(1.5)

    logger.info(f"X API search '{query}': {len(all_tweets)} tweets found")
    return all_tweets


def fetch_tweet_replies(tweet_id: str, max_results: int = 20) -> list[TweetComment]:
    """Fetch replies to a specific tweet via search API.

    Uses query `conversation_id:{id} is:reply` to find replies.
    """
    api_url = "https://api.x.com/2/tweets/search/recent"
    query = f"conversation_id:{tweet_id} is:reply"

    all_comments: list[TweetComment] = []
    next_token = None
    pages = 0
    max_pages = (max_results + 9) // 10

    while pages < max_pages:
        params = {
            "query": query,
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics,author_id,in_reply_to_user_id,conversation_id",
            "expansions": "author_id",
            "user.fields": "username,name",
            "sort_order": "relevancy",
        }
        if next_token:
            params["next_token"] = next_token

        data = _make_request(api_url, params)
        if not data or not data.get("data"):
            break

        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

        for reply in data["data"]:
            metrics = reply.get("public_metrics", {})
            author = users.get(reply.get("author_id"), {})

            c = TweetComment(
                id=reply["id"],
                author_username=author.get("username", ""),
                author_name=author.get("name", ""),
                text=reply.get("text", ""),
                created_at=reply.get("created_at", ""),
                likes=metrics.get("like_count", 0),
                replies=metrics.get("reply_count", 0),
                views=metrics.get("impression_count", 0),
                url=f"https://x.com/{author.get('username', '')}/status/{reply['id']}",
            )
            c.compute_score()
            all_comments.append(c)

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break
        pages += 1
        time.sleep(1.2)

    logger.info(f"X API replies to {tweet_id}: {len(all_comments)} found")
    return all_comments


def sort_by_engagement(tweets: list[Tweet]) -> list[Tweet]:
    """Sort tweets by engagement score (pre-computed)."""
    for t in tweets:
        t.compute_score()
    return sorted(tweets, key=lambda t: t.engagement_score, reverse=True)


def sort_comments(comments: list[TweetComment]) -> list[TweetComment]:
    """Sort comments by engagement score (pre-computed)."""
    for c in comments:
        c.compute_score()
    return sorted(comments, key=lambda c: c.engagement_score, reverse=True)
