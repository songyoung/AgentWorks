# AgentWorks

通用 Agent 开发框架，基于 **LangGraph + Loop Engineering 四阶段循环 + Deep Agents Harness 中间件栈**。

## 定位

AgentWorks 不是一个具体的 Agent，而是一套**可复用的 Agent 构建工具链**。所有复杂 Agent（代码审查、日志分析、脚本流程梳理、测试生成等）均基于此框架开发，通过注册不同的工具（Tool）和技能（Skill）来定制行为。

> 框架是平台，Agent 是应用。框架代码在 `src/agentworks/` 中保持纯净（零硬编码工具），所有自定义 Agent 在 `workspace/agents/` 中独立开发。

---

## 核心工作流

AgentWorks 的核心是一个**自循环、自纠错**的 Agent 执行引擎。每个 Agent 的运行都经历以下完整生命周期：

```
                        ┌─────────────┐
                        │   START     │
                        └──────┬──────┘
                               │
                               ▼
                     ┌─────────────────┐
                     │     GATHER      │
                     │  输入解析       │
                     │  上下文压缩     │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
            ┌───────│     ACTION      │◄──────┐
            │        │  工具调用       │       │
            │        │  任务执行       │       │
            │        └────────┬────────┘       │
            │                 │                │
            │                 ▼                │
            │        ┌─────────────────┐       │
            │        │     VERIFY      │       │
            │        │  质量评估       │       │
            │        │  多维度打分     │       │
            │        └────────┬────────┘       │
            │                 │                │
            │                 ▼                │
            │        ┌─────────────────┐       │
            │        │     REPEAT      │       │
            │        │  条件路由       │       │
            │        │  重试控制       │       │
            │        └────────┬────────┘       │
            │                 │                │
            │     ┌───────────┼───────────┐    │
            │     │           │           │    │
            │     ▼           ▼           ▼    │
            │  ┌──────┐  ┌────────┐  ┌────────┐│
            │  │ END  │  │GATHER  │  │ACTION  ││
            │  │ 完成 │  │优化上下│  │重试执行││
            │  └──────┘  │  文    │  │        ││
            │            └────────┘  └────────┘│
            │                       ▲         │
            └───────────────────────┘         │
                                              │
              重试循环（最多 max_retries 次）──┘
```

### 四阶段详解

#### 1. GATHER — 输入解析与上下文压缩

```
raw_input（任务描述）
       │
       ▼
  ┌──────────────┐    首次？    ┌──────────────────┐
  │ parsed_      │───────────→│ LLM 解析          │
  │ structure    │    Yes      │ intent / entities │
  │ 是否为空？   │             │ / constraints     │
  └──────┬───────┘             └──────────────────┘
         │ No（重试回退）
         ▼
  ┌──────────────┐   超阈值？   ┌──────────────────┐
  │ messages     │───────────→│ 保留最近 N 条     │
  │ Token 计数   │    Yes      │ + LLM 生成摘要    │
  └──────────────┘             └──────────────────┘
         │
         ▼
  输出：parsed_structure + context_summary
```

- 首次执行：调用 LLM 将自然语言任务解析为结构化 JSON（意图、实体、约束）
- 后续执行（feedback 含 "context"）：检查消息历史 Token 是否超 `context_token_limit`
- 超限时保留最近 `keep_recent_messages` 条，其余压缩为滚动摘要
- **可配置**：`configs/loop_spec.yaml` → `context_token_limit`（8000）、`keep_recent_messages`（5）

#### 2. ACTION — 工具调用与任务执行

```
TOOL_REGISTRY（已注册工具列表）
       │
       ▼
  ┌──────────────┐   有工具？   ┌──────────────────┐
  │ get_all_     │───────────→│ 顺序执行所有工具  │
  │ tools()      │    Yes      │ tool_1 → tool_2 → │
  └──────┬───────┘             │ 每个返回 dict     │
         │ No                  │ 合并到 state       │
         ▼                    └──────────────────┘
  ┌──────────────┐
  │ LLM 直接生成 │              ┌──────────────────┐
  │ task_plan +  │              │ 提取输出:        │
  │ generated_   │              │ task_plan        │
  │ output       │              │ generated_output │
  └──────────────┘              └──────────────────┘
```

- 优先执行 `TOOL_REGISTRY` 中已注册的工具函数（顺序执行，后面的工具可见前面的变更）
- 无工具时 LLM 直接生成 `task_plan`（执行计划）和 `generated_output`（输出内容）
- 工具函数签名：`(state: dict) -> dict`，返回仅需更新的字段
- **约束 R3**：所有 action 调用的函数必须注册

#### 3. VERIFY — 质量评估与反馈

```
generated_output + task_plan
       │
       ▼
  ┌──────────────┐            ┌──────────────────┐
  │ LLMJudge     │───────────→│ LLM 多维度评估   │
  │ evaluate()   │            │ accuracy    (30%) │
  └──────────────┘            │ completeness(25%) │
                              │ clarity     (20%) │
                              │ relevance   (15%) │
                              │ safety      (10%) │
                              └────────┬─────────┘
                                       │
                                       ▼
                               quality_score (0~1)
                               feedback (改进建议)
```

- 调用 LLMJudge 对输出进行 5 维度加权评分
- 产出 `quality_score`（0.0~1.0）和 `feedback`（可操作改进建议）
- **约束 R5**：verify 节点不得调用任何执行工具，确保评估独立
- **可配置**：`configs/prompts/verifier.yaml` → 维度权重、阈值、评分模式

#### 4. REPEAT — 条件路由与重试控制

```
quality_score + feedback
       │
       ▼
  ┌──────────────┐
  │ retry_count  │  ← 每次进入 +1
  │ += 1         │
  └──────┬───────┘
         │
         ▼
  ╔══════════════════════════════════════════════╗
  ║              条件路由判断                     ║
  ╠══════════════════════════════════════════════╣
  ║ is_complete = True?          → END（终止）   ║
  ║ quality_score >= 0.7?        → END（达标）   ║
  ║ feedback 含 "context"?       → GATHER        ║
  ║ 其他                          → ACTION        ║
  ║                                              ║
  ║ retry_count >= max_retries?  → 强制 END      ║
  ╚══════════════════════════════════════════════╝
```

- 每次进入 `retry_count += 1`
- 质量达标（≥0.7）→ 终止；需优化上下文 → 回到 gather；否则 → 回到 action
- **约束 R6**：`retry_count >= max_retries` 时强制 `is_complete = True`，防止无限循环
- **可配置**：`configs/loop_spec.yaml` → `max_retries`（3）、`quality_threshold`（0.7）

---

## 完整工作流时序

```
时间 ──────────────────────────────────────────────────────────────→

  用户输入
    │
    ▼
  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐
  │GATHER│──→│ACTION│──→│VERIFY│──→│REPEAT│──→ END
  └──────┘   └──────┘   └──────┘   └──────┘     │
      解析      执行        评估        路由       │
      raw      tools     LLMJudge    retry++     │
       ↓        ↓          ↓           ↓         │
    parsed   task_plan  score=0.5   score<0.7   │
    struct   gen_out    feedback   → ACTION ────┘
                                                │
                         ┌──────────────────────┘
                         ▼
                      ┌──────┐   ┌──────┐   ┌──────┐
                      │ACTION│──→│VERIFY│──→│REPEAT│──→ END ✓
                      └──────┘   └──────┘   └──────┘
                       重试        再评      score=0.85
                                              达标!
```

---

## 快速开始

### 环境要求

- Python >= 3.11
- uv 包管理器
- OpenAI API Key（或 Anthropic API Key）

### 安装

```bash
git clone https://github.com/songyoung/AgentWorks.git
cd AgentWorks
uv venv .venv --python 3.11
uv pip install -e ".[dev]"
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入 API Key
# OPENAI_API_KEY=sk-xxx
```

### 运行

```bash
# 通用 CLI：输入任意任务描述
uv run agentworks --input "你的任务描述"

# 或运行已有的自定义 Agent
cd workspace
uv run python agents/script_flow/run.py --input sample_script.py
```

---

## 开发自定义 Agent

### 标准开发流程

```
1. 创建 Agent 目录     workspace/agents/my_agent/
                           │
2. 编写工具 tools.py       @register_tool 注册工具函数
                           │
3. 编写入口 run.py         导入工具 → 组装状态 → 调用 graph
                           │
4. 声明 Skill（可选）      SKILL_REGISTRY 预置键名
                           │
5. 运行验证                cd workspace && python agents/my_agent/run.py --input xxx
```

### 示例：脚本流程梳理 Agent

**项目结构**：

```
workspace/
├── agents/
│   └── script_flow/
│       ├── __init__.py
│       ├── tools.py         ← 两个 @register_tool 工具
│       └── run.py           ← Agent 独立启动入口
└── sample_script.py         ← 测试脚本
```

**tools.py — 定义工具**：

```python
from agentworks.tools import register_tool
from agentworks.core.llm import get_default_llm

@register_tool
def parse_script_structure(state: dict) -> dict:
    """LLM 解析脚本控制流：入口/函数/分支/循环/异常"""
    script = state.get("raw_input", "")
    llm = get_default_llm(temperature=0.0)
    response = llm.invoke(f"分析以下脚本结构:\n{script}")
    # ... 解析 response 返回结构化数据 ...
    return {"parsed_structure": {...}}

@register_tool
def generate_flow_report(state: dict) -> dict:
    """基于解析结果生成 Mermaid 流程图 + 分析报告"""
    flow = state.get("parsed_structure", {}).get("flow_analysis", {})
    llm = get_default_llm(temperature=0.1)
    # ... 生成 Mermaid + 报告 ...
    return {"generated_output": [{"mermaid": "...", "report": {...}}]}
```

**run.py — 启动入口**：

```python
from agents.script_flow import tools        # 触发 @register_tool
from agentworks.core.graph import get_graph
from agentworks.checkpoints.store import create_checkpointer

state = {"raw_input": script_content, ...}   # 组装初始状态

with create_checkpointer() as cp:
    graph = get_graph(checkpointer=cp)
    final_state = graph.invoke(state, config) # 运行四阶段循环

print(final_state["generated_output"])       # 输出结果
```

### 工具函数约定

| 项目 | 约定 |
|------|------|
| 参数 | `state: dict` — 当前 AgentState 字典 |
| 返回 | `dict` — 仅包含需要更新的字段 |
| 注册 | `@register_tool` 装饰器 |
| 执行 | action 节点中顺序调用 |

### Skill 注册

```python
from agentworks.tools.skill_tools import register_skill

# 预置键名已在 SKILL_REGISTRY 中声明
register_skill("script_flow_analysis", MySkillClass)
```

---

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                      AgentWorks                           │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Harness 中间件栈                      │    │
│  │  TodoList → Filesystem → Summarization → HITL    │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │           Loop Engineering 四阶段循环              │    │
│  │                                                   │    │
│  │   ┌────────┐    ┌────────┐    ┌────────┐          │    │
│  │   │ GATHER │───→│ ACTION │───→│ VERIFY │          │    │
│  │   │ 解析   │    │ 执行   │    │ 评估   │          │    │
│  │   └────────┘    └────────┘    └────┬───┘          │    │
│  │       ▲                            │              │    │
│  │       │         ┌────────┐         │              │    │
│  │       └─────────│ REPEAT │◄────────┘              │    │
│  │                 │ 路由   │                        │    │
│  │                 └────┬───┘                        │    │
│  │                      │                            │    │
│  │              ┌───────┴───────┐                    │    │
│  │              ▼               ▼                    │    │
│  │         ┌────────┐     ┌──────────┐               │    │
│  │         │  END   │     │ 重试循环 │               │    │
│  │         └────────┘     └──────────┘               │    │
│  └───────────────────────────────────────────────────┘    │
│                         │                                │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │   工具注册表    │   技能注册表    │   评估器      │    │
│  │   TOOL_        │   SKILL_       │   LLMJudge    │    │
│  │   REGISTRY     │   REGISTRY     │               │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
AgentWorks/
├── configs/
│   ├── loop_spec.yaml          # 循环规格（阈值/重试/路由/Token）
│   ├── harness_spec.yaml       # 中间件栈规格（4 层中间件顺序）
│   └── prompts/
│       └── verifier.yaml       # 评估维度（5 维度 × 加权平均）
│
├── src/agentworks/             # 框架核心（禁止硬编码 Agent 逻辑）
│   ├── core/
│   │   ├── state.py            # AgentState 字段契约 (TypedDict)
│   │   ├── config.py           # Pydantic 配置加载 + 环境变量覆盖
│   │   ├── llm.py              # LLM 客户端工厂 + 显式 fallback
│   │   └── graph.py            # StateGraph 拓扑 + 四节点实现
│   ├── middleware/
│   │   └── __init__.py         # 中间件加载顺序（从 config 读取）
│   ├── checkpoints/
│   │   └── store.py            # SQLite SqliteSaver 持久化
│   ├── tools/
│   │   ├── __init__.py         # TOOL_REGISTRY + register_tool
│   │   └── skill_tools.py      # SKILL_REGISTRY + register_skill
│   ├── verifiers/
│   │   └── judge.py            # LLMJudge 多维度评估器
│   └── cli/
│       └── main.py             # CLI 入口 + 图执行
│
├── workspace/                  # Agent 开发与运行时
│   └── agents/                 # ✅ 自定义 Agent（Git 跟踪）
│       └── script_flow/        # 示例：脚本流程梳理 Agent
│           ├── tools.py
│           └── run.py
│
├── tests/                      # 测试目录
├── .workbuddy_rules            # 8 条确定性工程硬约束
├── .env.example                # 环境变量模板
├── pyproject.toml              # 项目元数据与依赖
└── .gitignore                  # workspace/* 忽略，!workspace/agents/
```

---

## 配置系统

三份 YAML 配置文件通过 Pydantic 模型加载，支持环境变量覆盖：

| 文件 | 模型 | 关键参数 |
|------|------|----------|
| `loop_spec.yaml` | `LoopSpec` | max_retries=3, quality_threshold=0.7, context_token_limit=8000 |
| `harness_spec.yaml` | `HarnessSpec` | 4 中间件顺序, checkpoint 表名 |
| `verifier.yaml` | `VerifierSpec` | 5 维度权重, scoring_mode=standard |

环境变量覆盖规则：`loop.max_retries` → `LOOP_MAX_RETRIES=5`

---

## 参数速查

| 参数 | 值 | 来源 |
|------|-----|------|
| 最大重试次数 | 3 | `loop_spec.yaml` |
| 质量阈值 | 0.7 | `loop_spec.yaml` |
| 上下文 Token 限制 | 8000 | `loop_spec.yaml` |
| 保留最近消息数 | 5 | `loop_spec.yaml` |
| 路由标签 | continue / retry / refine_context | `loop_spec.yaml` |
| 中间件顺序 | TodoList→Filesystem→Summarization→HITL | `harness_spec.yaml` |
| HITL 审批动作 | write_file / edit_file / delete_file | `harness_spec.yaml` |
| 检查点表名 | agentworks_checkpoints | `harness_spec.yaml` |
| 评估维度 | accuracy(30%) + completeness(25%) + clarity(20%) + relevance(15%) + safety(10%) | `verifier.yaml` |

---

## 确定性工程规则

| 规则 | 要点 |
|------|------|
| R1 状态契约先行 | 先更新 AgentState，再引用新字段 |
| R2 节点职责单一 | Gather/Action/Verify/Repeat 不交叉 |
| R3 工具强制注册 | Action 调用的函数必须注册 |
| R4 技能预先声明 | 新 Skill 先在 SKILL_REGISTRY 预置键名 |
| R5 评估生成隔离 | Verify 不调用任何执行工具 |
| R6 重试防失控 | retry_count >= max_retries 强制结束 |
| R7 配置外置 | 所有阈值从 YAML 读取 |
| R8 LLM 回退显式 | 调用外部模型处声明 fallback |

---

## 依赖

| 类别 | 库 |
|------|-----|
| LangGraph 生态 | langgraph, langgraph-checkpoint-sqlite |
| Harness 基础层 | deepagents |
| LLM 网关 | langchain-openai, langchain-anthropic |
| 数据库 | aiosqlite |
| 配置管理 | pydantic, pydantic-settings |
| Token 计数 | tiktoken |
| 可观测性 | langsmith |

## License

MIT
