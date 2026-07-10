"""配置加载模块 —— Pydantic 模型化 YAML 配置。

规则 R7: 所有业务阈值从此模块读取，禁止在其他代码中硬编码。
支持通过同名环境变量覆盖 YAML 配置值（环境变量名 = 路径大写 + 下划线）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ── 辅助：加载 YAML 文件 ──


def _load_yaml(relative_path: str) -> dict[str, Any]:
    """加载 YAML 配置文件，返回解析后的字典。

    Args:
        relative_path: 相对于项目根目录 configs/ 的路径。

    Returns:
        解析后的字典。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
    """
    configs_dir = Path(__file__).resolve().parent.parent.parent.parent / "configs"
    file_path = configs_dir / relative_path
    if not file_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {file_path}")
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env_override(key: str, default: Any) -> Any:  # noqa: ANN401
    """检查环境变量覆盖，格式: 路径大写+下划线。

    例如 loop.max_retries → LOOP_MAX_RETRIES。
    """
    env_key = key.replace(".", "_").upper()
    env_val = os.environ.get(env_key)
    if env_val is None:
        return default
    # 类型转换：尝试保持原类型
    if isinstance(default, bool):
        return env_val.lower() in ("true", "1", "yes")
    if isinstance(default, int):
        return int(env_val)
    if isinstance(default, float):
        return float(env_val)
    return env_val


# ── Loop 规格模型 ──


class RouteTags(BaseModel):
    """路由标签配置。"""

    continue_: str = Field(alias="continue", default="continue")
    retry: str = "retry"
    refine_context: str = "refine_context"

    model_config = {"populate_by_name": True}


class LoopNodes(BaseModel):
    """四阶段节点名称。"""

    gather: str = "gather"
    action: str = "action"
    verify: str = "verify"
    repeat: str = "repeat"


class LoopSpec(BaseModel):
    """Loop Engineering 四阶段循环规格。

    从 configs/loop_spec.yaml 加载。
    所有字段可通过同名环境变量（如 LOOP_MAX_RETRIES=5）覆盖。
    """

    nodes: LoopNodes = Field(default_factory=LoopNodes)
    max_retries: int = 3
    quality_threshold: float = 0.7
    context_token_limit: int = 8000
    keep_recent_messages: int = 5
    route_tags: RouteTags = Field(default_factory=RouteTags)

    @classmethod
    def load(cls) -> LoopSpec:
        """从 YAML 加载并应用环境变量覆盖。"""
        raw = _load_yaml("loop_spec.yaml")
        loop_data = raw.get("loop", {})

        # 应用环境变量覆盖
        for key, default in cls.model_fields.items():
            env_key = f"loop.{key}"
            if key in ("nodes", "route_tags"):
                continue
            if isinstance(default.default, (int, float, bool, str)):
                loop_data[key] = _env_override(env_key, loop_data.get(key, default.default))

        return cls.model_validate(loop_data)


# ── Harness 规格模型 ──


class MiddlewareConfig(BaseModel):
    """单个中间件配置。"""

    name: str
    module: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class CheckpointConfig(BaseModel):
    """检查点存储配置。"""

    table_name: str = "agentworks_checkpoints"
    db_path_env: str = "CHECKPOINT_DB_PATH"
    default_db_path: str = "./agentworks_checkpoints.db"


class HarnessSpec(BaseModel):
    """Harness 中间件栈规格。

    从 configs/harness_spec.yaml 加载。
    """

    middleware_order: list[MiddlewareConfig] = Field(default_factory=list)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)

    @classmethod
    def load(cls) -> HarnessSpec:
        """从 YAML 加载 Harness 配置。"""
        raw = _load_yaml("harness_spec.yaml")
        harness_data = raw.get("harness", {})
        return cls.model_validate(harness_data)


# ── Verifier 规格模型 ──


class DimensionConfig(BaseModel):
    """评估维度配置。"""

    name: str
    weight: float
    description: str = ""


class FeedbackConfig(BaseModel):
    """反馈配置。"""

    detailed: bool = True
    max_suggestions: int = 3


class VerifierSpec(BaseModel):
    """评估器配置规格。

    从 configs/prompts/verifier.yaml 加载。
    """

    dimensions: list[DimensionConfig] = Field(default_factory=list)
    scoring_mode: str = "standard"
    passing_threshold: float = 0.7
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)

    @classmethod
    def load(cls) -> VerifierSpec:
        """从 YAML 加载 Verifier 配置。"""
        raw = _load_yaml("prompts/verifier.yaml")
        verifier_data = raw.get("verifier", {})
        return cls.model_validate(verifier_data)


# ── 单例加载（模块 import 时自动执行） ──


@lru_cache(maxsize=1)
def get_loop_spec() -> LoopSpec:
    """获取 Loop 规格单例。"""
    return LoopSpec.load()


@lru_cache(maxsize=1)
def get_harness_spec() -> HarnessSpec:
    """获取 Harness 规格单例。"""
    return HarnessSpec.load()


@lru_cache(maxsize=1)
def get_verifier_spec() -> VerifierSpec:
    """获取 Verifier 规格单例。"""
    return VerifierSpec.load()
