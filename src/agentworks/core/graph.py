"""图拓扑 —— Loop Engineering 四阶段循环的 LangGraph StateGraph。

节点职责（规则 R2）:
- gather:  输入解析 + Token 阈值上下文压缩
- action:  工具调用与任务执行
- verify:  质量评估与反馈（规则 R5: 不调用任何工具）
- repeat:  条件路由 + 重试防失控（规则 R6）
"""

from __future__ import annotations

import json
from typing import Any, Literal

import tiktoken
from langgraph.graph import END, StateGraph

from agentworks.core.config import get_loop_spec, get_verifier_spec
from agentworks.core.llm import get_default_llm
from agentworks.core.state import AgentState
from agentworks.tools import get_all_tools
from agentworks.verifiers.judge import LLMJudge

# ── Token 计数工具 ──

_encoder = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """计算文本的 Token 数量。"""
    return len(_encoder.encode(text))


def _count_messages_tokens(messages: list) -> int:
    """计算消息列表的总 Token 数。"""
    total = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        total += _count_tokens(content)
    return total


# ── gather 节点 ──


def gather_node(state: AgentState) -> dict[str, Any]:
    """gather: 输入解析 + Token 阈值上下文压缩。

    1. 首次执行: 将 raw_input 解析为结构化 parsed_structure
    2. 后续执行 (refine_context): 压缩消息历史
    3. 若 Token 超限: 保留最近 N 条消息 + 生成滚动摘要
    """

    spec = get_loop_spec()
    updates: dict[str, Any] = {}

    # ── 步骤 1: 输入解析（首次） ──
    if not state.get("parsed_structure"):
        llm = get_default_llm(temperature=0.0)
        parse_prompt = (
            "请将以下用户输入解析为结构化表示，输出 JSON 格式。\n"
            "包含以下字段：intent（意图）、entities（实体列表）、"
            "constraints（约束条件）、output_format（期望输出格式）。\n\n"
            f"用户输入：\n{state['raw_input']}"
        )
        response = llm.invoke(parse_prompt)
        content = response.content if hasattr(response, "content") else str(response)
        try:
            parsed = json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            parsed = {"intent": content, "entities": [], "constraints": [], "output_format": "text"}
        updates["parsed_structure"] = parsed

    # ── 步骤 2: Token 计数与上下文压缩 ──
    messages = state.get("messages", [])
    if messages:
        token_count = _count_messages_tokens(messages)
        if token_count > spec.context_token_limit:
            keep_n = spec.keep_recent_messages
            # 保留最近 N 条
            recent = messages[-keep_n:] if len(messages) > keep_n else messages
            # 对早期消息生成摘要
            early = messages[:-keep_n] if len(messages) > keep_n else []
            if early:
                llm = get_default_llm(temperature=0.0)
                early_text = "\n".join(m.get("content", "") if isinstance(m, dict) else str(m) for m in early)
                summary_prompt = f"请将以下对话历史压缩为简洁的摘要，保留关键信息和决策。\n\n{early_text}"
                summary_response = llm.invoke(summary_prompt)
                summary = summary_response.content if hasattr(summary_response, "content") else str(summary_response)
                prev_summary = state.get("context_summary", "")
                updates["context_summary"] = (
                    f"{prev_summary}\n[摘要]\n{summary}" if prev_summary else f"[摘要]\n{summary}"
                )
                updates["messages"] = recent  # 替换为压缩后的消息列表

    return updates


# ── action 节点 ──


def action_node(state: AgentState) -> dict[str, Any]:
    """action: 工具调用与任务执行。

    策略:
    1. 若有已注册的工具 → 顺序执行所有工具
    2. 若无工具 → 直接用 LLM 生成输出
    3. 产出 task_plan 和 generated_output
    """
    updates: dict[str, Any] = {}
    tools = get_all_tools()

    if tools:
        # ── 有工具: 顺序执行 ──
        current_state = dict(state)
        for tool in tools:
            try:
                result = tool(current_state)
                if isinstance(result, dict):
                    current_state.update(result)
            except Exception as e:
                updates.setdefault("messages", [])
                updates["messages"].append({"role": "system", "content": f"工具 {tool.__name__} 执行异常: {e}"})

        # 提取 tool 产生的 task_plan 和 output
        if "task_plan" in current_state:
            updates["task_plan"] = current_state["task_plan"]
        if "generated_output" in current_state:
            updates["generated_output"] = current_state["generated_output"]
    else:
        # ── 无工具: LLM 直接生成 ──
        llm = get_default_llm(temperature=0.3)
        parsed = state.get("parsed_structure", {})
        context = state.get("context_summary", "")

        action_prompt = (
            "你是一个任务执行 Agent。根据以下信息生成任务计划和输出内容。\n\n"
            f"## 用户输入\n{state['raw_input']}\n\n"
            f"## 解析结构\n{json.dumps(parsed, ensure_ascii=False, indent=2)}\n\n"
        )
        if context:
            action_prompt += f"## 上下文摘要\n{context}\n\n"
        action_prompt += (
            "请输出 JSON，包含：\n- task_plan: 执行计划（步骤列表）\n- generated_output: 各步骤的输出结果列表\n"
        )

        response = llm.invoke(action_prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content_clean = content.strip().removeprefix("```json").removesuffix("```").strip()

        try:
            result = json.loads(content_clean)
            updates["task_plan"] = result.get("task_plan", [])
            updates["generated_output"] = result.get("generated_output", [])
        except json.JSONDecodeError:
            updates["task_plan"] = [{"step": 1, "details": "直接生成", "tool_required": "none"}]
            updates["generated_output"] = [{"content": content}]

    return updates


# ── verify 节点 ──


def verify_node(state: AgentState) -> dict[str, Any]:
    """verify: 质量评估与反馈生成。

    调用 LLMJudge 对 generated_output 进行多维度评估。
    规则 R5: 不得调用任何 TOOL_REGISTRY 中的工具。
    """
    verifier_spec = get_verifier_spec()
    judge = LLMJudge(
        criteria=[d.model_dump() for d in verifier_spec.dimensions],
        threshold=verifier_spec.passing_threshold,
        mode=verifier_spec.scoring_mode,
    )

    content = {
        "generated_output": state.get("generated_output", []),
        "task_plan": state.get("task_plan", []),
    }
    context = {
        "raw_input": state.get("raw_input", ""),
        "parsed_structure": state.get("parsed_structure", {}),
        "feedback": state.get("feedback", ""),
    }

    result = judge.evaluate(content, context)

    return {
        "quality_score": result.score,
        "feedback": result.feedback,
    }


# ── repeat 节点 ──


def repeat_node(state: AgentState) -> dict[str, Any]:
    """repeat: 条件路由 + 重试计数。

    规则 R6: retry_count >= max_retries 时强制结束。
    不包含业务逻辑，仅负责路由决策和计数管理。
    """
    retry_count = state.get("retry_count", 0) + 1
    max_retries = state.get("max_retries", get_loop_spec().max_retries)

    updates: dict[str, Any] = {"retry_count": retry_count}

    if retry_count >= max_retries:
        updates["is_complete"] = True
        updates["feedback"] = state.get("feedback", "") + (f"\n[系统] 已达最大重试次数 ({max_retries})，强制终止。")

    return updates


# ── 条件路由 ──


def should_continue(state: AgentState) -> Literal["__end__", "gather", "action"]:
    """verify 之后的条件路由判断。

    Returns:
        "__end__": 任务完成或质量达标
        "gather": 需要优化上下文
        "action": 需要重试执行
    """
    if state.get("is_complete", False):
        return END

    score = state.get("quality_score", 0.0)
    loop_spec = get_loop_spec()
    if score >= loop_spec.quality_threshold:
        return END

    feedback = state.get("feedback", "")
    if "context" in feedback.lower():
        return "gather"

    return "action"


# ── 图构建 ──


def build_graph() -> StateGraph:
    """构建通用四阶段循环的 StateGraph。

    拓扑: START → gather → action → verify → repeat → [条件路由]
          条件路由: END | gather | action
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("gather", gather_node)
    workflow.add_node("action", action_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("repeat", repeat_node)

    workflow.set_entry_point("gather")
    workflow.add_edge("gather", "action")
    workflow.add_edge("action", "verify")
    workflow.add_edge("verify", "repeat")

    workflow.add_conditional_edges(
        "repeat",
        should_continue,
        {
            END: END,
            "gather": "gather",
            "action": "action",
        },
    )

    return workflow


_graph: StateGraph | None = None


def get_graph(checkpointer: Any = None) -> StateGraph:  # noqa: ANN401
    """获取编译后的图实例。

    Args:
        checkpointer: 可选的检查点存储实例（如 SqliteSaver）。

    Returns:
        编译后的 StateGraph。
    """
    builder = build_graph()
    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
