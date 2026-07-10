"""技能注册表 —— 管理所有科室能力（Skill）的声明与加载。

规则 R4: 新增 Skill 须在 SKILL_REGISTRY 中预置键名，初始值为 None。
后续实现加载器时替换为实际类。
"""

# ruff: noqa: ANN401  — 注册表模式允许 Any 类型
from __future__ import annotations

from typing import Any

# ── 技能注册表 ──
# 预置五个 Skill 键名，值初始为 None（占位）
# 后续实现加载器时替换为实际类实例
SKILL_REGISTRY: dict[str, Any] = {
    "code_review": None,  # 代码审查
    "log_analysis": None,  # 日志分析
    "jira_ticket": None,  # Jira 工单管理
    "test_generation": None,  # 测试用例生成
    "hmi_rule_check": None,  # HMI 规则检查
    "script_flow_analysis": None,  # 脚本流程梳理
}


def register_skill(name: str, skill_cls: Any) -> None:
    """注册一个 Skill 类到注册表。

    Args:
        name: Skill 键名（如 "code_review"）。
        skill_cls: Skill 类或实例。

    Raises:
        KeyError: 若键名不在预置的 SKILL_REGISTRY 中。
    """
    if name not in SKILL_REGISTRY:
        raise KeyError(f"Skill '{name}' 未在 SKILL_REGISTRY 中预置键名。 可用键名: {list(SKILL_REGISTRY.keys())}")
    SKILL_REGISTRY[name] = skill_cls


def get_skill(name: str) -> Any:
    """获取已注册的 Skill。

    Args:
        name: Skill 键名。

    Returns:
        Skill 类或实例，若未加载则返回 None。
    """
    return SKILL_REGISTRY.get(name)


def get_all_skill_names() -> list[str]:
    """返回所有已声明的 Skill 键名。"""
    return list(SKILL_REGISTRY.keys())
