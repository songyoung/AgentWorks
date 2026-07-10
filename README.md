# AgentWorks

通用 Agent 开发框架，基于 **LangGraph + Loop Engineering 四阶段循环 + Deep Agents Harness 中间件栈**。

## 定位

AgentWorks 不是一个具体的 Agent，而是一套**可复用的 Agent 构建工具链**。所有复杂 Agent（PPT 生成、代码审查、日志分析、测试生成等）均基于此框架开发，通过注册不同的工具（Tool）和技能（Skill）来定制行为。

## 架构

```
┌──────────────────────────────────────────────┐
│                  AgentWorks                   │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │        Harness 中间件栈               │   │
│   │  TodoList → Filesystem → Summary → HITL │ │
│   └──────────────────────────────────────┘   │
│                      │                       │
│   ┌──────────────────▼────────────────────┐  │
│   │     Loop Engineering 四阶段循环        │  │
│   │                                       │  │
│   │   Gather ──→ Action ──→ Verify        │  │
│   │      ▲                      │         │  │
│   │      └────── Repeat ◄───────┘         │  │
│   └──────────────────────────────────────┘  │
│                      │                       │
│   ┌──────────────────▼────────────────────┐  │
│   │    工具注册表 · 技能注册表 · 评估器     │  │
│   └──────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 四阶段循环

| 阶段 | 节点 | 职责 |
|------|------|------|
| Gather | `gather_node` | 输入解析 + Token 阈值上下文压缩 |
| Action | `action_node` | 工具调用与任务执行（仅调用已注册工具） |
| Verify | `verify_node` | LLM 多维度质量评估（不调用任何工具） |
| Repeat | `repeat_node` | 条件路由判断 + 重试防失控 |

### 中间件栈

| 顺序 | 中间件 | 用途 |
|------|--------|------|
| 1 | TodoListMiddleware | 任务规划与跟踪 |
| 2 | FilesystemMiddleware | 工作目录文件读写 |
| 3 | SummarizationMiddleware | 上下文 Token 阈值压缩 |
| 4 | HumanInTheLoopMiddleware | 关键操作人工审批 |

## 快速开始

### 环境要求

- Python >= 3.11
- uv 包管理器

### 安装

```bash
git clone <repo-url> AgentWorks
cd AgentWorks
uv venv .venv --python 3.11
uv pip install -e ".[dev]"
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 等必要密钥
```

### 运行

```bash
uv run agentworks --input "你的任务描述"
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` | 是 | — | 任务描述文本 |
| `--thread-id` | 否 | 自动生成 UUID | 会话隔离标识 |
| `--max-retries` | 否 | 3 | 最大重试次数 |

## 目录结构

```
AgentWorks/
├── configs/
│   ├── loop_spec.yaml          # 循环规格（阈值/重试/路由）
│   ├── harness_spec.yaml       # 中间件栈规格
│   └── prompts/
│       └── verifier.yaml       # 评估维度配置
├── src/agentworks/
│   ├── core/
│   │   ├── state.py            # AgentState 字段契约
│   │   └── graph.py            # StateGraph 拓扑
│   ├── middleware/
│   │   └── __init__.py         # 中间件加载顺序
│   ├── checkpoints/
│   │   └── store.py            # SQLite 检查点配置
│   ├── tools/
│   │   ├── __init__.py         # TOOL_REGISTRY 工具注册表
│   │   └── skill_tools.py      # SKILL_REGISTRY 技能注册表
│   ├── verifiers/
│   │   └── judge.py            # LLMJudge 评估器
│   └── cli/
│       └── main.py             # CLI 入口
├── workspace/                   # 运行时工作区（gitignore）
├── tests/                       # 测试目录
├── .workbuddy_rules             # 确定性工程硬约束
├── .env.example                 # 环境变量模板
├── pyproject.toml               # 项目元数据与依赖
└── .gitignore
```

## 开发指南

### 构建自定义 Agent

```python
from agentworks.core.state import AgentState
from agentworks.tools import register_tool

# 1. 注册自定义工具
@register_tool
def my_custom_tool(state: AgentState) -> AgentState:
    """你的工具逻辑"""
    return state

# 2. （可选）注册自定义 Skill
from agentworks.tools.skill_tools import register_skill
register_skill("my_skill", MySkillClass)

# 3. 启动框架
from agentworks.cli.main import main
main(["--input", "你的任务描述"])
```

### 确定性工程规则

所有代码生成与修改必须遵守 `.workbuddy_rules` 中定义的 8 条硬约束：

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

## 依赖

| 类别 | 库 |
|------|-----|
| LangGraph 生态 | langgraph |
| Harness 基础层 | deepagents |
| LLM 网关 | langchain-openai, langchain-anthropic |
| 数据库 | aiosqlite |
| 配置管理 | pydantic, pydantic-settings |
| Token 计数 | tiktoken |
| 可观测性 | langsmith |

## License

MIT
