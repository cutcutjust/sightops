# XAgent

X 平台 AI 调研与操作 Agent — 纯 API 快速调研 + 视觉深度采集 + 发推互动。

**核心能力**：X API 搜索发现 → 高热度排序 → 纯 API 快速采集 / 视觉深度采集 → 发推互动。

**技术栈**：Qwen3.6-Plus（视觉）· X API v2（Bearer Token + OAuth 1.0a）· PyAutoGUI（全局控制）· Notion API · SQLite · Rich CLI

---

## 快速上手

```bash
# 1. 创建虚拟环境并安装
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. 全局可用（可选）
echo 'alias xagent="/Users/justyn/SightOps/xagent/.venv/bin/xagent"' >> ~/.zshrc
source ~/.zshrc

# 3. 初始化项目
xagent setup

# 3. 编辑 .env，填入 LLM API Key 和 X API 凭证
#    LLM_API_KEY=sk-xxx
#    X_API_BEARER_TOKEN=xxx（纯 API 模式必需）
#    X_API_CONSUMER_KEY=xxx（OAuth 1.0a，发推/互动必需）

# 4. 开始调研
xagent research "AI agent"

# 5. 查看状态
xagent status
```

> 如果没有配置全局 alias，需要先 `source /Users/justyn/SightOps/xagent/.venv/bin/activate` 激活虚拟环境。
```

> **系统授权**：仅 `--mode visual` 需要（系统设置 → 隐私与安全性 → 屏幕录制 + 辅助功能 → 启用终端 → 重启 Terminal）。纯 API 模式无需任何权限。

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `xagent setup` | 初始化项目（首次使用）— 检查 Python/配置/权限/数据库 |
| `xagent research "主题"` | X 调研（默认纯 API，`--mode visual` 用视觉深度采集）→ 热度排序 → 实时保存 MD + Notion |
| `xagent report "主题"` | 生成调研报告 — 基于权重排序的来源，带引用 |
| `xagent analyze` | 爆款风格分析 — 对已采集内容做钩子/结构/叙事模式统计 |
| `xagent write` | 根据调研生成草稿 — 提取风格 → 通用草稿 → 平台适配 |
| `xagent publish` | 发布草稿到 X — 纯视觉操作 |
| `xagent status` | 数据总览 — 采集统计 / 待发布草稿 / 内容排行榜 |
| `xagent observe` | 实时屏幕观察器 — 全屏截图 + LLM 分析 |

---

## 使用流程

### Step 0 — 初始化

```bash
xagent setup
```

自动完成：检查 Python 环境 → 验证 LLM 配置 → 创建目录结构 → 初始化 SQLite → 检查 macOS 权限。

### Step 1 — 调研

```bash
# 纯 API 模式（默认，无需桌面权限）
xagent research "AI agent" --limit 50 --min-comments 10

# 视觉深度采集模式（需 macOS 权限，提取图片/完整正文）
xagent research "AI agent" --mode visual

# 使用 topics.yaml 默认关键词
xagent research
```

**API 调研流程**（默认）：

```
X API 搜索关键词 → 按互动量排序 (likes + reposts*1.5 + replies*2 + views*0.01)
  ↓
逐个采集 → API 正文/指标/媒体 → API 获取评论(10+ 条，按赞排序)
  ↓
LLM 相关性打分 → 摘要 + 标签
  ↓
★ 实时保存: SQLite + 本地 MD 文件 + Notion
  ↓
下一个帖子 → 直到目标数量
```

每个帖子完整采集：
- **正文**：API 直接获取完整文本 + 外部链接（visual 模式通过视觉提取）
- **图片**：API 返回媒体 URL（visual 模式可视觉分析图片内容）
- **评论**：X API 获取 10+ 条，按点赞量排序（visual 模式 API 失败时视觉回退）
- **指标**：点赞/转发/评论/阅读/收藏
- **链接**：API 直接提供精确 URL
- **实时保存**：每帖立即保存到 SQLite + 本地 MD（`data/research_md/`）+ Notion
- **权重打分**：likes + reposts*1.5 + replies*2 + views*0.01

> **紧急终止**：鼠标移到屏幕左上角（PyAutoGUI FAILSAFE）

### Step 1.5 — 生成报告

```bash
# 生成调研报告（带引用）
xagent report "AI Agent 趋势"

# 生成文章
xagent report "AI Agent 趋势" --type article

# 生成摘要
xagent report "AI Agent 趋势" --type summary
```

基于权重排序的来源（按互动量加载到提示词），生成的报告包含引用标注：`[来源N]（@用户名，❤赞数）`。

### Step 2 — 分析

```bash
# 分析最近 7 天的爆款风格
xagent analyze

# 分析最近 30 天
xagent analyze --days 30
```

统计热门开头类型、叙事结构模式、内容风格分布。

### Step 3 — 写作

```bash
# 生成长文
xagent write --type article --topic "AI Agent 趋势"

# 生成 Thread
xagent write --type thread

# 生成短帖
xagent write --type short_post
```

流程：提取 Top K 来源风格 → 生成通用草稿 → 适配平台格式 → 预览保存。

### Step 4 — 发布

```bash
# 查看状态和草稿
xagent status

# 发布最新草稿
xagent publish
```

---

## 配置

### `.env` 文件

```bash
# ── LLM（必需）─
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.6-plus
LLM_VISION_MODEL=qwen3.6-plus

# ── Notion（可选）─
NOTION_TOKEN=ntn_xxx
NOTION_RESEARCH_DB_ID=xxx
NOTION_TEMPLATE_DB_ID=xxx
NOTION_DRAFT_DB_ID=xxx

# ── X API（纯 API 模式必需，视觉模式可选）─
X_API_BEARER_TOKEN=xxx          # App-Only Auth，搜索/评论优先使用
X_API_CONSUMER_KEY=xxx          # OAuth 1.0a，发推/点赞/关注等用户操作
X_API_CONSUMER_SECRET=xxx
X_API_ACCESS_TOKEN=xxx
X_API_ACCESS_TOKEN_SECRET=xxx

# ── 其他 ─
LOG_LEVEL=INFO
DATA_DIR=./data
DESKTOP_MAX_CYCLES=20
```

### Notion 数据库设置

1. 在 Notion 中创建一个数据库（或在 XAgent Research 页面中添加）
2. 确保包含以下属性：`名称`（标题）、`Platform`（单选）、`URL`（链接）、`Relevance`（数字）、`Likes`（数字）、`Tags`（多选）、`Collected`（日期）、`Status`（单选）、`Author`（文本）、`Published URL`（链接）
3. 将 Integration 分享到该数据库
4. 将数据库 ID 填入 `.env`

> 如果数据库属性不匹配，运行 `python scripts/notion_editor.py fix` 自动修复。

### `configs/topics.yaml`

配置默认搜索关键词：

```yaml
keywords:
  - "AI agent"
  - "vibe coding"
  - "LLM"
```

### `configs/app.yaml`

调整研究/写作参数：

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

### ComputerAgent — 纯视觉循环大脑

```
每次循环:
  1. SEE:   全屏截图 (macOS screencapture)
  2. THINK: LLM 分析截图 + 历史上下文 + 全局计划 → 输出 JSON 动作计划
  3. ACT:   PyAutoGUI 执行动作（move/click/type/hotkey/scroll）
  4. VERIFY: 下一次循环的截图天然构成验证
  5. 循环直到任务完成 / 卡住 / 达到最大循环数
```

- observe + decide 合并为一次 LLM 调用
- **计划上下文注入**：每次调用传入 `plan_context`（整体目标/当前步骤/下一步），LLM 在 prompt 中看到 `OVERALL PLAN`（✓已完成 → 当前 → 下一步）
- **重复 done 检测**：连续 2 次报告"完成"但无实际动作 → 主动退出
- 对话历史上下文，模型能看到页面变化
- 卡住检测：连续 8 次相同动作 → 终止
- LLM 输出归一化：坐标提取、文本提取、快捷键映射

### 执行器

- **拟人鼠标**：贝塞尔曲线 + 随机抖动 + 自适应速度
- **拟人输入**：随机打字间隔 + 偶尔思考停顿
- **坐标系统**：1000×1000 归一化 → 自动映射到实际分辨率

### 研究流程

```
APIXResearcher（默认，--mode api）
  └── discover()      API 搜索 + 按热度排序 + 实时保存
        ├── X API v2 search_tweets()  Bearer Token 分页获取 50+ 帖子
        ├── sort_by_engagement()      权重排序
        ├── _collect_and_save_tweet()  逐个采集，实时保存
        │     ├── 直接从 API Tweet 取正文/指标/媒体
        │     ├── fetch_tweet_replies()    API 获取 10+ 评论，按赞排序
        │     ├── LLM 相关性打分 + 摘要 + 标签
        │     ├── save_content()           SQLite 保存
        │     ├── save_content_to_md()     本地 MD 文件
        │     └── sync_to_notion()         Notion 同步

DesktopXResearcher（--mode visual）
  ├── discover()      API 搜索 + 视觉深度采集 + 实时保存
  │     ├── X API v2 search_tweets()  分页获取 50+ 帖子
  │     ├── sort_by_engagement()      权重排序: likes + reposts*1.5 + replies*2 + views*0.01
  │     ├── _collect_and_save_tweet()  逐个采集，实时保存
  │     │     ├── _collect_post_content()  视觉提取正文/指标
  │     │     ├── fetch_tweet_replies()    API 获取 10+ 评论，按赞排序
  │     │     ├── _analyze_images()        点击打开图片 → 视觉分析
  │     │     ├── save_content()           SQLite 保存（含评论表）
  │     │     ├── save_content_to_md()     本地 MD 文件（data/research_md/）
  │     │     └── _sync_to_notion()        Notion 同步
  │     └── 回退方案：API 评论失败 → 视觉评论
  └── _go_back()       返回
```

### 报告生成

```
generate_report(topic)
  ├── load_collected_content()   加载最近 N 天数据
  ├── 按 engagement_score 排序   likes + reposts*1.5 + replies*2 + views*0.01
  ├── 构建提示词                 Top 20 来源 + 评论 + 引用标注
  ├── LLM 生成报告               3 种类型: research / article / summary
  ├── save_report_to_file()      本地 MD 文件（data/reports/）
  └── 引用格式                   [来源N]（@用户名，❤赞数）
```

### 数据流

```
SQLite 本地存储
  ├── CollectedContent  采集的帖子（正文/指标/图片/评论）
  ├── Comment           评论内容
  ├── Reference         浏览/跳过的 URL 记录
  ├── Task              任务记录
  ├── UniversalDraft    通用草稿
  └── PlatformDraft     平台适配草稿
```

---

## 项目结构

```
app/
  cli/               Typer CLI 入口（美化 Rich 界面）
  core/              配置 · 错误 · 日志
  schemas/           数据模型
  llm/               LLM 客户端（OpenAI 兼容）
  research/           纯 API 调研（无需浏览器/桌面权限）
    api_researcher.py    API 调研 Agent
  desktop/           桌面级纯视觉控制
    computer_agent.py    核心 see-think-act-verify 循环
    executor.py          PyAutoGUI 执行器（人类化行为）
    observer.py          screencapture 全屏截图
    research_agent.py    X 深度调研 Agent
    publisher.py         X 发布器
    permissions.py       macOS 权限检查
  observer/          实时屏幕观察器
  analysis/          爆款风格挖掘
  writing/           内容生成
  integrations/      Notion API
  memory/            SQLite 本地存储
  platforms/         平台插件（可扩展）
scripts/
  notion_editor.py   Notion 数据库管理（inspect/fix/create）
configs/           YAML 配置
prompts/           LLM prompt 模板
data/              运行时数据（screenshots / drafts / cache / runs）
```

---

## 扩展

只需添加 `app/platforms/<name>/` 目录实现平台规则即可。核心视觉循环（ComputerAgent）无需修改。
