"""Research report generation from weighted sources."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings, load_yaml
from app.core.logger import logger
from app.llm.client import chat
from app.memory.sqlite_repo import load_collected_content


def _format_source_block(c, rank: int) -> str:
    """Format a single source with its content and top comments for the report prompt."""
    top_comments = sorted(c.comments, key=lambda cm: cm.likes, reverse=True)[:10]

    lines = [
        f"[{rank}] **@{c.author}** | ❤ {c.metrics.likes} | 🔁 {c.metrics.reposts} | 💬 {len(c.comments)} | 👁 {c.metrics.views} | ⭐ 权重: {c.engagement_score:.0f}",
        f"URL: {c.source_url}",
        f"正文:\n{c.body_text}",
    ]

    if c.summary:
        lines.append(f"\n摘要: {c.summary}")

    if c.images:
        lines.append(f"\n图片: {'; '.join(c.images[:3])}")

    if top_comments:
        lines.append(f"\n热门评论 ({len(top_comments)}条):")
        for i, cm in enumerate(top_comments, 1):
            lines.append(f"  {i}. @{cm.author or '?'} (❤{cm.likes}): {cm.text[:200]}")

    if c.tags:
        lines.append(f"\n标签: {', '.join(c.tags)}")

    return "\n".join(lines)


def _build_sources_prompt(sources, max_sources: int = 20) -> str:
    """Build the sources section for the report generation prompt."""
    # Sort by engagement score
    sorted_sources = sorted(sources, key=lambda c: getattr(c, 'engagement_score', c.relevance_score), reverse=True)
    selected = sorted_sources[:max_sources]

    blocks = []
    for i, s in enumerate(selected, 1):
        blocks.append(_format_source_block(s, i))

    return "\n\n---\n\n".join(blocks)


async def generate_report(topic: str, days: int = 7, report_type: str = "research") -> str:
    """Generate a research report or article from collected sources.

    Args:
        topic: Research topic
        days: Lookback days for content
        report_type: 'research' | 'article' | 'summary'

    Returns:
        Full markdown report string
    """
    sources = load_collected_content(days=days)
    if not sources:
        return "没有采集到数据。先运行 xagent research。"

    # Filter by topic relevance
    topic_sources = [s for s in sources if s.relevance_score >= 3.0 or topic.lower() in s.body_text.lower()[:200]]
    if not topic_sources:
        topic_sources = sources[:20]

    # Compute engagement scores
    for s in topic_sources:
        s.engagement_score = s.metrics.likes + s.metrics.reposts * 1.5 + len(s.comments) * 2 + s.metrics.views * 0.01

    sources_text = _build_sources_prompt(topic_sources)

    prompt_templates = {
        "research": (
            f"你是一位资深研究员。基于以下 {len(topic_sources)} 条高权重 X 帖子来源（按点赞量和评论量加权排序），"
            f"撰写一份关于「{topic}」的深度调研报告。\n\n"
            "要求：\n"
            "1. 有清晰的章节结构（引言 → 核心发现 → 观点分析 → 趋势总结 → 结论）\n"
            "2. 每个重要观点必须引用来源，格式：[来源N]（@用户名，❤赞数）\n"
            "3. 引用高评论量的评论作为佐证\n"
            "4. 分析帖子之间的关联性和矛盾点\n"
            "5. 给出 3-5 个核心洞察\n"
            "6. 全文用中文撰写\n\n"
            f"## 来源数据（按权重排序）\n\n{sources_text}"
        ),
        "article": (
            f"你是一位顶级内容创作者。基于以下 {len(topic_sources)} 条高权重 X 帖子来源（按互动量排序），"
            f"撰写一篇关于「{topic}」的高质量文章。\n\n"
            "要求：\n"
            "1. 吸引人的标题\n"
            "2. 故事化叙述，用数据支撑\n"
            "3. 每个关键论点引用来源：[来源N]（@用户名）\n"
            "4. 语言风格：专业但不枯燥，有洞察力\n"
            "5. 结尾给出行动建议\n"
            "6. 全文中文\n\n"
            f"## 来源数据\n\n{sources_text}"
        ),
        "summary": (
            f"基于以下 {len(topic_sources)} 条 X 帖子，撰写一份关于「{topic}」的精简总结。\n\n"
            "要求：\n"
            "1. 300-500 字\n"
            "2. 列出 Top 5 核心观点\n"
            "3. 每个观点标注来源 [来源N]\n"
            "4. 中文\n\n"
            f"## 来源\n\n{sources_text}"
        ),
    }

    prompt = prompt_templates.get(report_type, prompt_templates["research"])

    result = await chat(
        [{"role": "user", "content": prompt}],
        max_tokens=4096, temperature=0.3,
    )

    # Add metadata header
    header = (
        f"# {topic} — 调研报告\n\n"
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"> 类型: {report_type}\n"
        f"> 来源数量: {len(topic_sources)} 条 X 帖子\n"
        f"> 数据来源: X API 搜索 + 视觉深度采集\n\n"
        "---\n\n"
    )

    return header + result.strip()


def save_report_to_file(markdown: str, topic: str) -> str:
    """Save report to local MD file. Returns file path."""
    s = get_settings()
    report_dir = s.data_path / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    from slugify import slugify
    safe_topic = slugify(topic) or "report"
    filename = f"{safe_topic}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    filepath = report_dir / filename

    filepath.write_text(markdown, encoding="utf-8")
    logger.info(f"Report saved: {filepath}")
    return str(filepath)
