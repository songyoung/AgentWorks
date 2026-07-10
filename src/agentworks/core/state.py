"""全局状态定义 —— AgentState 字段契约。

规则 R1: 新增字段须先更新此处的 TypedDict 定义。
规则 R6: repeat 节点检查 retry_count >= max_retries 时强制结束。

AgentState 是所有基于 AgentWorks 构建的 Agent 的通用状态容器。
具体 Agent 可继承或扩展此状态以添加领域特定字段。
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Agent 通用状态对象。

    所有字段必须在此显式声明，其他模块通过此定义访问状态。
    LangGraph 使用 TypedDict 定义状态通道，messages 字段使用 add_messages
    注解实现消息自动追加（而非覆盖）。

    适用场景：任何遵循 Loop Engineering 四阶段循环的 Agent。
    """

    # ── 输入与会话 ──
    raw_input: str
    """用户输入的原始文本 / 任务描述。"""

    thread_id: str
    """会话隔离标识，默认使用 UUID。"""

    # ── 解析与上下文 ──
    parsed_structure: dict[str, Any]
    """解析后的结构化表示，形式由具体 Agent 定义。"""

    context_summary: str
    """当原始消息超阈值时的滚动摘要。"""

    # ── 规划与生成 ──
    task_plan: list[dict[str, Any]]
    """推理后的任务执行计划，每项含 step / details / tool_required。"""

    generated_output: list[dict[str, Any]]
    """各步骤已生成的输出内容列表。"""

    # ── 评估与反馈 ──
    quality_score: float
    """评估分数（0.0 ~ 1.0）。"""

    feedback: str
    """可操作的改进建议字符串。"""

    # ── 对话历史 ──
    messages: Annotated[list, add_messages]
    """对话历史，使用 add_messages 注解实现自动追加。"""

    # ── 重试控制 ──
    retry_count: int
    """当前重试轮次，从 0 开始计数。"""

    max_retries: int
    """最大重试次数，默认值 3，可通过 CLI 参数覆盖。"""

    # ── 终止标志 ──
    is_complete: bool
    """任务完成标志，True 时图执行终止。"""
