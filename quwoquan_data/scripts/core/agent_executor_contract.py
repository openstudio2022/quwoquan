"""会话 agent = 唯一模型执行者 契约（防回归静态门）。

固化用户硬约束：内容生产的"模型处理"全部在受治理编程助手 provider 内完成，
当前只允许 Cursor SDK 或官方 Codex Python SDK adapter，禁止其他 LLM 客户端/SDK、
静默 provider fallback 或降级生成路径冒充交付内容。

校验三条：
A. scripts/ 内禁止 import 外部 LLM SDK、或出现 LLM 服务 HTTP 端点字面量
   （会话 agent 是唯一模型执行者，不得旁路到外部模型服务）。
B. 交付正文 generator 必须由 ContentGenerator 闭集控制：materialize 保留
   "非 agent 拒绝落地"逻辑，draft_io 暴露 AGENT/PENDING 状态。
C. 脚本占位主页（_stub_entity_page）必须带透明占位标记，不得冒充模型创作内容。

本模块为纯静态扫描（无运行期副作用、确定性），供 test/verify 调用。
"""
from __future__ import annotations

from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]

# 外部 LLM SDK / 本地大模型服务（受治理 adapter 之外），一律禁止进入生产脚本。
_FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "zhipuai",
    "dashscope",
    "cohere",
    "replicate",
    "ollama",
    "qianfan",
    "llama_cpp",
    "google.generativeai",
    "google_genai",
    "vllm",
)
# LLM 服务端点字面量（即便用裸 http 调用也要拦住）。
_FORBIDDEN_ENDPOINTS = (
    "api.openai.com",
    "api.anthropic.com",
    "dashscope.aliyuncs.com",
    "generativelanguage.googleapis.com",
    "open.bigmodel.cn",
    "api.cohere.ai",
    ":11434",  # ollama 默认端口
)

# 本文件自身定义了上述禁止词常量，扫描时跳过，避免自指误报。
_SELF_NAME = "agent_executor_contract.py"


def _iter_py_files(scripts_root: Path):
    for path in sorted(scripts_root.rglob("*.py")):
        if path.name == _SELF_NAME:
            continue
        yield path


def _scan_forbidden_executors(scripts_root: Path) -> list[str]:
    issues: list[str] = []
    for path in _iter_py_files(scripts_root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(scripts_root)
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                tokens = stripped.replace("import ", " ").replace("from ", " ").split()
                head = tokens[0] if tokens else ""
                for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                    if head == prefix or head.startswith(prefix + "."):
                        issues.append(
                            f"{rel}:{lineno}: forbidden LLM SDK import '{head}' "
                            f"(会话 agent 是唯一模型执行者，禁止外部 LLM 客户端)"
                        )
            for endpoint in _FORBIDDEN_ENDPOINTS:
                if endpoint in line:
                    issues.append(
                        f"{rel}:{lineno}: forbidden LLM endpoint '{endpoint}' "
                        f"(禁止旁路到外部模型服务)"
                    )
    return issues


def _require_substring(scripts_root: Path, rel_path: str, needles: tuple[str, ...], why: str) -> list[str]:
    path = scripts_root / rel_path
    if not path.is_file():
        return [f"{rel_path}: missing (agent-executor contract anchor); {why}"]
    text = path.read_text(encoding="utf-8")
    missing = [n for n in needles if n not in text]
    if missing:
        return [f"{rel_path}: contract anchor weakened, missing {missing}; {why}"]
    return []


def scan_agent_executor_contract(scripts_root: Path | None = None) -> list[str]:
    root = scripts_root or SCRIPTS_ROOT
    issues: list[str] = []
    # A. 禁外部 LLM 执行者。
    issues.extend(_scan_forbidden_executors(root))
    issues.extend(
        _require_substring(
            root,
            "content/execution/agent/agent_runner.py",
            (
                "provider is AgentProvider.CURSOR_SDK",
                "provider is AgentProvider.CODEX_SDK",
                "unsupported semantic agent provider",
            ),
            "provider dispatch 必须闭集、显式且禁止静默 fallback",
        )
    )
    issues.extend(
        _require_substring(
            root,
            "content/execution/agent/codex_adapter.py",
            (
                "from openai_codex import ApprovalMode, Codex, Sandbox, is_retryable_error",
                "output_schema=_FINAL_RESPONSE_SCHEMA",
                "prompt=prompt",
            ),
            "Codex 必须使用官方 Python SDK、受治理 sandbox 和结构化最终输出",
        )
    )
    # B. 交付正文 agent-only 防线仍在。
    issues.extend(
        _require_substring(
            root,
            "content/post/materialize_apply.py",
            (
                "ContentGenerator.IMAGE_EVIDENCE_PACK.value",
                "ContentGenerator.AGENT.value",
            ),
            "materialize 必须拒绝非 agent generator 落地交付面",
        )
    )
    issues.extend(
        _require_substring(
            root,
            "content/post/article/draft_io.py",
            (
                "GENERATOR_AGENT = ContentGenerator.AGENT.value",
                "GENERATOR_PENDING = ContentGenerator.PENDING.value",
            ),
            "draft_io 必须冻结 agent/pending generator 契约",
        )
    )
    # C. 脚本占位主页保持透明标记，不冒充模型创作。
    issues.extend(
        _require_substring(
            root,
            "governance/coverage/entity_extract.py",
            ("content.post.entity_extract", "自动挖掘并建立"),
            "占位实体主页必须带透明 generatedBy 标记与占位声明",
        )
    )
    return issues


__all__ = ["SCRIPTS_ROOT", "scan_agent_executor_contract"]
