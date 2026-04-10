<div align="center">

# XAgent

**X 平台 AI 调研与操作 Agent**

纯 API 快速调研 · 视觉深度采集 · 发推互动

---

`research` → `report` → `analyze` → `write` → `publish`

</div>

---

## 特性

- **纯 API 调研** — 无需浏览器，无需桌面权限，Bearer Token 直连 X API
- **视觉深度采集** — 可选 `--mode visual`，截图 + 视觉模型提取图片/完整正文
- **热度排序** — 加权打分：likes + reposts×1.5 + replies×2 + views×0.01
- **实时保存** — 每帖立即持久化到 SQLite + 本地 MD + Notion
- **LLM 全链路** — 相关性打分、摘要、标签、风格分析、草稿生成
- **拟人操作** — 贝塞尔曲线鼠标 + 随机打字间隔 + 卡死检测

---

## 快速上手

```bash
# 1. 安装
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. 全局可用（可选）
echo 'alias xagent="/Users/justyn/SightOps/xagent/.venv/bin/xagent"' >> ~/.zshrc
source ~/.zshrc

# 3. 配置 .env
#    LLM_API_KEY=sk-xxx                          # 必需
#    X_API_BEARER_TOKEN=xxx                       # API 模式必需
#    X_API_CONSUMER_KEY=xxx                       # OAuth 1.0a，互动功能必需

# 4. 初始化
xagent setup

# 5. 调研
xagent research "AI agent"
```

> 纯 API 模式无需任何系统权限。`--mode visual` 需 macOS 屏幕录制 + 辅助功能授权。

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `xagent setup` | 初始化 — 检查环境 / 配置 / 权限 / 数据库 |
| `xagent research "主题"` | 调研 — `--mode api`（默认）或 `--mode visual` |
| `xagent report "主题"` | 报告 — `--type research\|article\|summary`，带引用 |
| `xagent analyze` | 分析 — 爆款风格：钩子类型 / 叙事结构 / 风格分布 |
| `xagent write` | 写作 — 提取风格 → 通用草稿 → 平台适配 |
| `xagent publish` | 发布 — 视觉操作发布到 X |
| `xagent status` | 总览 — 采集统计 / 草稿 / 排行 |
| `xagent observe` | 观察 — 实时截图 + LLM 分析 |

---

## 使用流程

### 调研

```bash
# 纯 API（默认，无需权限）
xagent research "AI agent" --limit 50 --min-comments 10

# 视觉深度采集（需 macOS 权限）
xagent research "AI agent" --mode visual

# 使用 topics.yaml 默认关键词
xagent research
```

```
X API 搜索 → 按热度排序 → 逐帖采集 → LLM 打分/摘要 → 实时保存
    │              │            │            │              │
    ▼              ▼            ▼            ▼              ▼
 Bearer      加权排序      正文/评论     相关性 1-5    SQLite + MD
 Token       Top 优先      指标/媒体     摘要+标签      + Notion
```

### 报告

```bash
xagent report "AI Agent 趋势"                    # 调研报告
xagent report "AI Agent 趋势" --type article     # 长文
xagent report "AI Agent 趋势" --type summary     # 摘要
```

引用格式：`[来源N]（@用户名，❤赞数）`

### 分析 → 写作 → 发布

```bash
xagent analyze --days 7                          # 爆款风格分析
xagent write --type article --topic "AI Agent"   # 生成草稿
xagent status                                    # 查看待发布
xagent publish                                   # 发布到 X
```

---

## 配置

### `.env`

```bash
# ── LLM（必需）─
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.6-plus
LLM_VISION_MODEL=qwen3.6-plus

# ── X API（API 模式必需）─
X_API_BEARER_TOKEN=xxx          # App-Only Auth，搜索/评论
X_API_CONSUMER_KEY=xxx          # OAuth 1.0a，发推/点赞/关注
X_API_CONSUMER_SECRET=xxx
X_API_ACCESS_TOKEN=xxx
X_API_ACCESS_TOKEN_SECRET=xxx

# ── Notion（可选）─
NOTION_TOKEN=ntn_xxx
NOTION_RESEARCH_DB_ID=xxx
NOTION_TEMPLATE_DB_ID=xxx
NOTION_DRAFT_DB_ID=xxx

# ── 其他 ─
LOG_LEVEL=INFO
DATA_DIR=./data
DESKTOP_MAX_CYCLES=20
```

### Notion 数据库

1. 创建数据库，包含属性：`名称`（标题）、`Platform`（单选）、`URL`（链接）、`Relevance`（数字）、`Likes`（数字）、`Tags`（多选）、`Collected`（日期）、`Status`（单选）、`Author`（文本）
2. 将 Integration 分享到该数据库
3. 填入 `.env`

> 属性不匹配？运行 `python scripts/notion_editor.py fix` 自动修复。

### configs/

**topics.yaml** — 默认搜索关键词

```yaml
keywords:
  - "AI agent"
  - "vibe coding"
  - "LLM"
```

**app.yaml** — 调研/写作参数

```yaml
research:
  topics_per_run: 10
  posts_per_topic: 30
  relevance_threshold: 3.0
writing:
  top_k_sources: 5
```

---

## 架构

### 双模式调研

```
APIXResearcher (--mode api)          DesktopXResearcher (--mode visual)
  │                                      │
  ├─ search_tweets() [Bearer]           ├─ search_tweets() [OAuth 1.0a]
  ├─ sort_by_engagement()               ├─ sort_by_engagement()
  ├─ _collect_and_save_tweet()          ├─ _collect_and_save_tweet()
  │   ├─ API 取正文/指标/媒体           │   ├─ 视觉提取正文/指标
  │   ├─ fetch_tweet_replies()          │   ├─ fetch_tweet_replies()
  │   ├─ LLM 打分 + 摘要 + 标签        │   ├─ 视觉图片分析
  │   └─ save → SQLite + MD + Notion    │   └─ save → SQLite + MD + Notion
  │                                      │
  └─ 无需浏览器/权限                     └─ 需 macOS 权限
```

### ComputerAgent — 视觉循环大脑（visual 模式）

```
SEE (截图) → THINK (LLM + 计划上下文) → ACT (拟人操作) → VERIFY (下一帧截图) → 循环
```

- 计划上下文注入：LLM 看到 `OVERALL PLAN`（已完成 → 当前 → 下一步）
- 卡死检测：连续 8 次相同动作 → 终止
- 重复完成检测：连续 2 次无实际动作 → 主动退出
- 拟人执行：贝塞尔曲线鼠标 + 随机打字间隔 + 1000×1000 归一化坐标

### 数据流

```
CollectedContent ──→ SQLite ──→ analyze / report / write
      │                │
      ├── 本地 MD       └── PlatformDraft ──→ publish
      └── Notion
```

---

## 项目结构

```
app/
  cli/               Typer CLI（Rich 美化）
  core/              配置 · 错误 · 日志
  schemas/           数据模型
  llm/               LLM 客户端（OpenAI 兼容）
  research/          纯 API 调研
    api_researcher.py    APIXResearcher
  desktop/           视觉桌面控制
    computer_agent.py    see-think-act-verify 循环
    executor.py          拟人执行器
    observer.py          截图观察
    research_agent.py    DesktopXResearcher + 公共 LLM 函数
    publisher.py         X 发布器
    permissions.py       macOS 权限
  observer/          实时屏幕观察
  analysis/          爆款风格挖掘
  writing/           内容生成
  integrations/      X API · Notion API
  memory/            SQLite 存储
  platforms/         平台插件（可扩展）
configs/             YAML 配置
prompts/             LLM 模板
data/                运行时数据
scripts/             工具脚本
```

---

## 扩展

添加 `app/platforms/<name>/` 目录实现平台规则。核心视觉循环和 API 调研器无需修改。
