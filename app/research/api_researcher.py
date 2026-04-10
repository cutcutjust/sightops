"""X 纯 API 调研器 — 无需浏览器/桌面权限，直接从 X API 获取所有数据。"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime

from app.core.config import load_yaml
from app.core.logger import logger
from app.llm.client import chat
from app.memory.sqlite_repo import save_content, save_reference, save_content_to_md
from app.desktop.research_agent import score_relevance, summarize_content, extract_tags, sync_to_notion
from app.schemas.content import CollectedContent, Comment
from rich.console import Console

console = Console()


class APIXResearcher:
    """X 调研 — 纯 API，无需 DesktopAgent / 浏览器 / macOS 权限。"""

    def __init__(self):
        self._collected_urls: set[str] = set()
        self._total_collected = 0

    # ── 主流程 ────────────────────────────────────────────────────────

    async def discover(self, topics: list[str] | None = None, target_posts: int = 50, min_comments: int = 10) -> list[dict]:
        """纯 API 调研流程。

        1. 用 X API 搜索每个主题
        2. 按互动量排序
        3. 对每个帖子：直接取 API 数据 → 获取评论(API) → LLM 打分/摘要
        4. 每采集完一个帖子立即保存到 SQLite + 本地 MD + Notion
        """
        cfg = load_yaml("configs/app.yaml")
        r = cfg["research"]
        topics_per_run = r.get("topics_per_run", 10)

        topic_cfg = load_yaml("configs/topics.yaml")
        if topics is None:
            topics = topic_cfg.get("keywords", [])

        all_posts: list[dict] = []
        posts_per_topic = max(target_posts // max(len(topics[:topics_per_run]), 1), 10)

        for topic in topics[:topics_per_run]:
            if self._total_collected >= target_posts:
                console.print(f"[dim]已达到目标 {target_posts} 个帖子，停止[/dim]")
                break

            console.print(f"\n[cyan]{'='*50}[/cyan]")
            console.print(f"[bold cyan]📡 API 搜索: {topic}[/bold cyan] (目标 {posts_per_topic} 帖)")
            console.print(f"[cyan]{'='*50}[/cyan]")

            try:
                from app.integrations.x_api import search_tweets, sort_by_engagement

                tweets = search_tweets(topic, max_results=posts_per_topic, sort_order="relevancy")
                if not tweets:
                    console.print(f"    [yellow]API 未返回结果[/yellow]")
                    continue

                tweets = sort_by_engagement(tweets)
                console.print(f"    [dim]API 返回 {len(tweets)} 条，按互动量排序[/dim]")

                for tweet in tweets:
                    if self._total_collected >= target_posts:
                        break

                    # 去重
                    if tweet.id in self._collected_urls:
                        continue
                    self._collected_urls.add(tweet.id)

                    post_data = await self._collect_and_save_tweet(
                        tweet, topic, min_comments=min_comments
                    )
                    if post_data:
                        all_posts.append(post_data)

                console.print(f"\n  [green]✓ {topic}: 已采集 {len([p for p in all_posts if p.get('topic') == topic])} 个帖子[/green]")
                await asyncio.sleep(random.uniform(2, 4))

            except Exception as e:
                console.print(f"    [yellow]搜索失败: {e}[/yellow]")
                continue

        logger.info(f"API 调研完成: 共采集 {self._total_collected} 个帖子")
        return all_posts

    # ── 单个帖子采集 + 实时保存 ──────────────────────────────────────

    async def _collect_and_save_tweet(self, tweet, topic: str, min_comments: int = 10) -> dict | None:
        """采集单个帖子（纯 API），立即保存到 MD + Notion + SQLite。"""
        from app.integrations.x_api import fetch_tweet_replies, sort_comments

        author = tweet.author_username
        console.print(f"\n  [dim]▶ @{author} ❤{tweet.likes} 💬{tweet.replies} 👁{tweet.views}")
        console.print(f"    {tweet.text[:80]}...")

        # 1. 直接从 API Tweet 对象构建 CollectedContent
        content_id = f"x:{author}:{tweet.id}"
        content = CollectedContent(
            content_id=content_id,
            platform="x",
            source_url=tweet.url,
            author=author,
            title="",
            body_text=tweet.text,
            external_links=self._extract_links(tweet.text),
            images=tweet.media if tweet.media else [],
        )
        content.metrics.likes = tweet.likes
        content.metrics.reposts = tweet.reposts
        content.metrics.replies = tweet.replies
        content.metrics.views = tweet.views
        content.metrics.bookmarks = 0

        if tweet.created_at:
            try:
                content.published_at = datetime.fromisoformat(tweet.created_at.replace("Z", "+00:00"))
            except Exception:
                pass

        console.print(
            f"      [dim]正文: {len(content.body_text)} 字 | "
            f"❤{content.metrics.likes} 🔁{content.metrics.reposts} "
            f"💬{content.metrics.replies} 👁{content.metrics.views}[/dim]"
        )

        # 2. 用 API 获取评论
        console.print(f"    [cyan]📥 获取评论...[/cyan]")
        comments = fetch_tweet_replies(tweet.id, max_results=max(min_comments, 15))
        if comments:
            comments = sort_comments(comments)
            content.comments = [
                Comment(author=c.author_username, text=c.text, likes=c.likes, url=c.url)
                for c in comments[:min_comments]
            ]
            console.print(f"    [dim]  获取到 {len(comments)} 条评论，取 Top {min_comments}[/dim]")
        else:
            console.print(f"    [dim]  无评论[/dim]")

        # 3. 相关性打分
        threshold = load_yaml("configs/app.yaml")["research"].get("relevance_threshold", 3.0)
        content.relevance_score = await score_relevance(content)
        if content.relevance_score < threshold:
            console.print(f"    [dim]  跳过 (相关性 {content.relevance_score:.1f} < {threshold})[/dim]")
            save_reference(content.source_url, "x", source="api", was_collected=False)
            return None

        # 4. 摘要 + 标签
        content.summary = await summarize_content(content)
        content.tags = await extract_tags(content)

        # 5. 计算综合权重
        content.engagement_score = (
            content.metrics.likes
            + content.metrics.reposts * 1.5
            + len(content.comments) * 2
            + content.metrics.views * 0.01
        )

        # ★ 实时保存
        save_content(content)
        md_path = save_content_to_md(content)
        console.print(
            f"    [green]✓ 已保存[/green] @{content.author} "
            f"| ❤{content.metrics.likes} 🔁{content.metrics.reposts} "
            f"| 💬{len(content.comments)} 👁{content.metrics.views} "
            f"| ⭐权重:{content.engagement_score:.0f} "
            f"| MD:{md_path.split('/')[-1]}"
        )

        save_reference(
            content.source_url, "x",
            content_id=content.content_id,
            title=f"@{content.author}: {content.body_text[:80]}",
            was_collected=True,
            source="api",
        )

        await sync_to_notion(content)
        self._total_collected += 1

        return {
            "author": author,
            "text_preview": tweet.text[:80],
            "topic": topic,
            "likes": content.metrics.likes,
            "views": content.metrics.views,
            "reposts": content.metrics.reposts,
            "replies": len(content.comments),
            "engagement_score": content.engagement_score,
        }

    # ── 辅助 ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_links(text: str) -> list[str]:
        """从推文文本中提取 URL。"""
        import re
        urls = re.findall(r'https?://[^\s]+', text)
        return urls
