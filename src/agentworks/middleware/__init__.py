"""中间件加载顺序列表。

规则 R7: 所有中间件参数从 configs/harness_spec.yaml 读取，禁止硬编码。
"""

from __future__ import annotations

from agentworks.core.config import get_harness_spec


def get_middleware_load_order() -> list[str]:
    """返回中间件名称列表（从 harness_spec.yaml 读取加载顺序）。"""
    spec = get_harness_spec()
    return [mw.name for mw in spec.middleware_order]


def get_middleware_configs() -> list[dict]:
    """返回中间件完整配置列表。"""
    spec = get_harness_spec()
    return [mw.model_dump() for mw in spec.middleware_order]
