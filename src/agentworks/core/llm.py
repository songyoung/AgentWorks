"""LLM 客户端工厂 —— 统一创建 langchain ChatModel。

规则 R8: 任何调用外部模型处须显式声明 fallback 行为。
本模块提供 create_llm 和 create_llm_with_fallback 两个工厂函数。
"""

from __future__ import annotations

import os
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

# ── 可用的模型提供方及其环境变量 ──

Provider = Literal["openai", "anthropic"]

_PROVIDER_CONFIG: dict[Provider, dict[str, str]] = {
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
}


def _get_provider_from_model(model: str) -> Provider:
    """从模型名称推断提供商。

    Args:
        model: 模型名称（如 "gpt-4o"、"claude-sonnet-4-20250514"）。

    Returns:
        提供商标识符。

    Raises:
        ValueError: 无法识别提供商时抛出。
    """
    model_lower = model.lower()
    if any(prefix in model_lower for prefix in ("gpt", "o1", "o3", "o4")):
        return "openai"
    if "claude" in model_lower:
        return "anthropic"
    raise ValueError(f"无法从模型名称 '{model}' 推断提供商。 请显式指定 provider 参数（'openai' 或 'anthropic'）。")


def _check_api_key(provider: Provider) -> None:
    """检查 API key 是否已配置。

    Args:
        provider: 提供商标识符。

    Raises:
        ValueError: 环境变量未设置时抛出。
    """
    cfg = _PROVIDER_CONFIG[provider]
    env_key = cfg["env_key"]
    if not os.environ.get(env_key):
        raise ValueError(f"{provider} API key 未配置。请设置环境变量 {env_key}。")


def create_llm(
    model: str | None = None,
    provider: Provider | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """创建 LLM 客户端（单一模型，无回退）。

    规则 R8: 调用方必须显式处理此函数可能抛出的异常，
    或使用 create_llm_with_fallback 声明回退链。

    Args:
        model: 模型名称。None 时使用提供商的默认模型。
        provider: 提供商（"openai" 或 "anthropic"）。
                  None 时从 model 名称推断。
        temperature: 生成温度（0.0 ~ 1.0），默认 0.0。

    Returns:
        langchain BaseChatModel 实例。

    Raises:
        ValueError: 模型/提供商不可用时抛出。
    """
    if provider is None:
        if model is None:
            # 默认：OpenAI GPT-4o
            provider = "openai"
            model = _PROVIDER_CONFIG["openai"]["default_model"]
        else:
            provider = _get_provider_from_model(model)

    if model is None:
        model = _PROVIDER_CONFIG[provider]["default_model"]

    _check_api_key(provider)

    if provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature)
    else:
        return ChatAnthropic(model=model, temperature=temperature)


def create_llm_with_fallback(
    primary_model: str,
    fallback_model: str,
    temperature: float = 0.0,
) -> BaseChatModel:
    """创建带显式回退链的 LLM 客户端。

    规则 R8: 回退行为在此显式声明，不隐式依赖单一模型。

    Args:
        primary_model: 主模型名称。
        fallback_model: 回退模型名称。
        temperature: 生成温度。

    Returns:
        带 fallback 的 langchain BaseChatModel。

    Raises:
        ValueError: 主模型和回退模型的 API key 均未配置时抛出。
    """
    primary = create_llm(model=primary_model, temperature=temperature)
    fallback = create_llm(model=fallback_model, temperature=temperature)
    return primary.with_fallbacks([fallback])


def get_default_llm(temperature: float = 0.0) -> BaseChatModel:
    """获取默认 LLM 客户端。

    优先级: OPENAI_API_KEY → ANTHROPIC_API_KEY。
    两者都未配置时抛出异常。
    """
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if openai_key:
        return create_llm(provider="openai", temperature=temperature)
    if anthropic_key:
        return create_llm(provider="anthropic", temperature=temperature)

    raise ValueError("未配置任何 LLM API key。请设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY。")
