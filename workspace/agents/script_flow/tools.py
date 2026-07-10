"""脚本流程梳理工具 —— 分析脚本控制流并生成 Mermaid 流程图。

工具链:
  1. parse_script_structure: LLM 深度解析脚本结构
  2. generate_flow_report: 基于解析结果生成 Mermaid 图 + 分析报告
"""

from __future__ import annotations

import json
import re
from typing import Any

from agentworks.core.llm import get_default_llm
from agentworks.tools import register_tool


@register_tool
def parse_script_structure(state: dict[str, Any]) -> dict[str, Any]:
    """深度分析脚本的控制流结构。

    读取 raw_input 中的脚本代码，调用 LLM 识别:
    - 编程语言和入口点
    - 函数/方法定义及调用关系
    - 条件分支 (if/else/switch/match)
    - 循环结构 (for/while/递归)
    - 异常处理 (try/except/finally)
    - 外部依赖和 I/O 调用
    - 数据流向

    Args:
        state: 当前 AgentState 字典。

    Returns:
        包含 flow_analysis 的 parsed_structure 更新。
    """
    script = state.get("raw_input", "")
    if not script.strip():
        return {
            "parsed_structure": {"error": "输入为空，无法分析"},
            "task_plan": [{"step": 0, "details": "输入为空", "tool_required": "none"}],
        }

    llm = get_default_llm(temperature=0.0)

    prompt = (
        "你是一个代码静态分析专家。请深度分析以下脚本的控制流结构。\n\n"
        "## 分析维度\n"
        "1. language: 编程语言\n"
        "2. entry_point: 程序入口（如 main 函数、顶层代码）\n"
        "3. functions: 所有函数/方法定义，含参数、返回值、调用关系\n"
        "4. branches: 条件分支（if/else/switch/match），含条件表达式和分支路径\n"
        "5. loops: 循环结构（for/while/递归），含循环条件和迭代变量\n"
        "6. error_handling: 异常处理（try/except/finally），含异常类型\n"
        "7. external_calls: 外部依赖调用（import、API、数据库、文件 I/O）\n"
        "8. data_flow: 关键变量的数据流向\n"
        "9. complexity_notes: 复杂度评估和改进建议\n\n"
        "## 脚本代码\n"
        "```\n"
        f"{script}\n"
        "```\n\n"
        "请输出严格的 JSON 格式（不要包含 markdown 代码块标记）:\n"
        "{\n"
        '  "language": "...",\n'
        '  "entry_point": "...",\n'
        '  "functions": [{"name": "...", "params": [], "returns": "...", "called_by": [], "calls": []}],\n'
        '  "branches": [{"type": "if/else/switch", "condition": "...", "paths": []}],\n'
        '  "loops": [{"type": "for/while/recursion", "condition": "...", "body_summary": "..."}],\n'
        '  "error_handling": [{"type": "try/except", "exceptions": [], "handler_summary": "..."}],\n'
        '  "external_calls": [{"type": "import/api/io", "target": "...", "purpose": "..."}],\n'
        '  "data_flow": [{"variable": "...", "source": "...", "consumers": []}],\n'
        '  "complexity_notes": "..."\n'
        "}\n"
    )

    try:
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        # 提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = {"raw_response": text, "parse_error": "无法提取 JSON"}
    except Exception as e:
        analysis = {"error": str(e)}

    # 合并到 parsed_structure
    existing = state.get("parsed_structure", {})
    if isinstance(existing, dict):
        existing["flow_analysis"] = analysis
    else:
        existing = {"flow_analysis": analysis}

    return {
        "parsed_structure": existing,
        "task_plan": [
            {"step": 1, "details": "解析脚本结构", "tool_required": "parse_script_structure"},
            {"step": 2, "details": "生成流程报告", "tool_required": "generate_flow_report"},
        ],
    }


@register_tool
def generate_flow_report(state: dict[str, Any]) -> dict[str, Any]:
    """基于结构分析生成 Mermaid 流程图和文字报告。

    读取 parsed_structure.flow_analysis，调用 LLM 生成:
    - Mermaid flowchart 代码
    - 结构化文字分析报告（概述、关键路径、风险点、优化建议）

    Args:
        state: 当前 AgentState 字典。

    Returns:
        包含 generated_output 的更新。
    """
    parsed = state.get("parsed_structure", {})
    flow_analysis = parsed.get("flow_analysis", {}) if isinstance(parsed, dict) else {}

    if not flow_analysis or "error" in flow_analysis:
        return {
            "generated_output": [{"error": "缺少结构分析结果，请先执行 parse_script_structure"}],
        }

    llm = get_default_llm(temperature=0.1)

    analysis_json = json.dumps(flow_analysis, ensure_ascii=False, indent=2)

    prompt = (
        "你是一个代码流程可视化专家。请基于以下脚本结构分析，生成流程报告。\n\n"
        "## 结构分析结果\n"
        f"{analysis_json}\n\n"
        "## 输出要求\n"
        "### 1. Mermaid 流程图\n"
        "生成一个 Mermaid flowchart TD (自上而下) 图，要求:\n"
        "- 以 entry_point 为起点\n"
        "- 展示所有函数节点\n"
        "- 标注条件分支路径（用菱形节点）\n"
        "- 标注循环回边\n"
        "- 标注异常处理路径（用虚线）\n"
        "- 使用中文标签\n"
        "- 节点数量控制在 15 个以内（合并次要步骤）\n\n"
        "### 2. 文字分析报告\n"
        "包含以下章节:\n"
        "- 概述: 一句话总结脚本功能\n"
        "- 关键路径: 主要执行路径描述\n"
        "- 分支逻辑: 条件判断和分支影响\n"
        "- 风险点: 潜在问题（异常未处理、死循环风险、资源泄漏等）\n"
        "- 优化建议: 可改进的方向\n\n"
        "请输出严格 JSON 格式:\n"
        "{\n"
        '  "mermaid": "flowchart TD\\n  A[开始] --> ...",\n'
        '  "report": {\n'
        '    "summary": "...",\n'
        '    "key_paths": ["..."],\n'
        '    "branch_logic": "...",\n'
        '    "risks": ["..."],\n'
        '    "suggestions": ["..."]\n'
        "  }\n"
        "}\n"
    )

    try:
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            report = json.loads(json_match.group())
        else:
            report = {"mermaid": "", "report": {"summary": text}}
    except Exception as e:
        report = {"mermaid": "", "report": {"summary": f"生成失败: {e}"}}

    return {
        "generated_output": [
            {
                "type": "flow_analysis_report",
                "mermaid": report.get("mermaid", ""),
                "report": report.get("report", {}),
                "language": flow_analysis.get("language", "unknown"),
                "entry_point": flow_analysis.get("entry_point", "未知"),
            }
        ],
        "task_plan": state.get("task_plan", []),
    }
