"""LLMJudge 评估器 —— LLM 驱动的多维度质量评估。

规则 R5: 评估器与执行逻辑隔离，verify 节点不得调用任何工具。

评估维度（从 configs/prompts/verifier.yaml 读取）:
  - accuracy    (0.30): 内容准确性
  - completeness(0.25): 内容完整性
  - clarity     (0.20): 表达清晰度
  - relevance   (0.15): 内容相关性
  - safety      (0.10): 安全合规
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agentworks.core.llm import get_default_llm


@dataclass
class EvaluationResult:
    """评估结果数据类。"""

    score: float
    """综合评分（0.0 ~ 1.0）。"""

    feedback: str
    """可操作的改进建议。"""

    passed: bool
    """是否通过阈值。"""

    dimension_scores: dict[str, float] = field(default_factory=dict)
    """各维度单独评分。"""


class LLMJudge:
    """LLM 驱动的多维度评估器。

    独立于执行图，仅用于 verify 节点。
    通过结构化 prompt 调用 LLM 对输出进行多维度评分。
    """

    def __init__(
        self,
        criteria: list[dict[str, Any]] | None = None,
        threshold: float = 0.7,
        mode: str = "standard",
    ) -> None:
        """初始化评估器。

        Args:
            criteria: 评估维度列表，每项含 name/weight/description。
            threshold: 通过阈值（0.0 ~ 1.0）。
            mode: 评分模式（"standard" 为加权平均，后续可扩展）。
        """
        self.criteria = criteria or []
        self.threshold = threshold
        self.mode = mode

    def evaluate(
        self,
        content: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """对生成内容进行多维度评估。

        Args:
            content: 待评估的内容字典（含 generated_output、task_plan）。
            context: 评估上下文（含 raw_input、parsed_structure）。

        Returns:
            EvaluationResult，包含加权分数、详细反馈、通过标志和维度得分。
        """
        if not self.criteria:
            return EvaluationResult(
                score=1.0,
                feedback="无评估维度配置，默认通过。",
                passed=True,
            )

        # ── 构建评估 prompt ──
        dimensions_desc = "\n".join(
            f"  {i + 1}. {c['name']} (权重 {c.get('weight', 0):.2f}): {c.get('description', '')}"
            for i, c in enumerate(self.criteria)
        )

        content_str = json.dumps(content, ensure_ascii=False, indent=2)
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "无"

        eval_prompt = (
            f"你是一个输出质量评估器。请根据以下维度对 Agent 的输出进行评分。\n\n"
            f"## 评估维度\n{dimensions_desc}\n\n"
            f"## 上下文/需求\n{context_str}\n\n"
            f"## Agent 输出\n{content_str}\n\n"
            f"## 评分要求\n"
            f"- 每个维度单独打分（0.0 ~ 1.0，保留 2 位小数）\n"
            f"- 给出综合分数（加权平均）\n"
            f"- 提供简洁的可操作改进建议\n"
            f"- 若之前已有反馈，判断是否已改进\n\n"
            f"请严格输出 JSON 格式：\n"
            f"{{\n"
            f'  "dimension_scores": {{"accuracy": 0.85, "completeness": 0.70, ...}},\n'
            f'  "overall_score": 0.78,\n'
            f'  "feedback": "具体改进建议",\n'
            f'  "issues_fixed": ["已修复问题列表"],\n'
            f'  "issues_remaining": ["待修复问题列表"]\n'
            f"}}\n"
        )

        # ── 调用 LLM 评估 ──
        try:
            llm = get_default_llm(temperature=0.0)
            response = llm.invoke(eval_prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            return EvaluationResult(
                score=0.0,
                feedback=f"评估 LLM 调用失败: {e}",
                passed=False,
            )

        # ── 解析评��结果 ──
        result = self._parse_response(response_text)
        return result

    def _parse_response(self, response_text: str) -> EvaluationResult:
        """从 LLM 响应中提取评估结果。

        Args:
            response_text: LLM 原始响应文本。

        Returns:
            EvaluationResult。
        """
        # 提取 JSON 块
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if not json_match:
            return EvaluationResult(
                score=0.5,
                feedback=f"无法解析评估结果: {response_text[:200]}",
                passed=False,
            )

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return EvaluationResult(
                score=0.5,
                feedback=f"评估结果 JSON 解析失败: {response_text[:200]}",
                passed=False,
            )

        # 提取维度得分
        dim_scores = data.get("dimension_scores", {})

        # 提取综合分数
        overall = data.get("overall_score", 0.0)
        if not isinstance(overall, (int, float)):
            overall = 0.0

        # 加权计算（若提供了 weights 且模式为 standard）
        if self.mode == "standard" and self.criteria and dim_scores:
            weighted = 0.0
            total_weight = 0.0
            for c in self.criteria:
                name = c["name"]
                weight = c.get("weight", 0)
                score = dim_scores.get(name, 0.0)
                weighted += score * weight
                total_weight += weight
            if total_weight > 0:
                overall = weighted / total_weight

        # 反��文本
        feedback_parts = [data.get("feedback", "")]
        remaining = data.get("issues_remaining", [])
        if remaining:
            feedback_parts.append("待修复: " + "; ".join(remaining))

        return EvaluationResult(
            score=round(float(overall), 4),
            feedback="\n".join(f for f in feedback_parts if f),
            passed=float(overall) >= self.threshold,
            dimension_scores=dim_scores,
        )
