"""工具注册表 —— 管理所有 Agent 可调用的工具函数。

规则 R3: 所有 action 节点调用的函数须在 TOOL_REGISTRY 中注册。
未注册的工具不得在 action 节点中使用。

具体 Agent 通过注册不同的工具集来定制行为。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ── 工具注册表 ──
# 初始为空列表，工具通过 register_tool() 追加
TOOL_REGISTRY: list[Callable[..., Any]] = []


def register_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """将函数注册到全局工具注册表。

    用法:
        @register_tool
        def my_tool(state: AgentState) -> AgentState:
            ...

    Args:
        func: 要注册的工具函数。

    Returns:
        原函数（不修改签名），同时追加到 TOOL_REGISTRY。
    """
    if func not in TOOL_REGISTRY:
        TOOL_REGISTRY.append(func)
    return func


def get_all_tools() -> list[Callable[..., Any]]:
    """返回所有已注册工具的列表。"""
    return list(TOOL_REGISTRY)
