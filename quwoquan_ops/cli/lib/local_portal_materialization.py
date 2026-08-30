"""本地 Portal 静态站点的物化。

与 dev-session runtime 编排是不同关注点：这里只负责把 ops-portal 前端产物落到
Caddy 的静态挂载根，或在工具链缺失时写显式占位页。

角色：lib。由 `quwoquan_ops/cli/commands/dev_session_runtime.py` 消费并经
`stackctl` 暴露。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

PORTAL_NOT_BUILT_PAGE = (
    "<!doctype html><html lang=\"zh\"><meta charset=\"utf-8\">"
    "<title>ops-portal 未构建</title><body>"
    "<h1>ops-portal 尚未构建</h1>"
    "<p>本地 Portal 静态产物缺失：请在 quwoquan_ops/portal 安装 node "
    "依赖后重新执行 stackctl dev-session / up，或运行 "
    "stackctl package --kind ops-portal。本页面是显式占位，"
    "不承载任何业务数据。</p></body></html>\n"
)


def materialize_local_portal_root(
    topology: dict[str, Any],
    target_name: str,
    portal_root: Path,
) -> str:
    """物化本地 Portal 静态站点到 Caddy /srv/portal 挂载根。

    具备仓内 node 工具链（portal/node_modules/.bin）与 QWQ_DEPLOY_WORK_ROOT
    时现场 vite build（base URL 从目标 publicBases 派生，不手写域名）；
    工具链缺失时写显式「未构建」提示页——本地开发环境不因前端缺构建阻塞
    服务栈启动，但绝不留下静默空 404 根目录。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    portal_dir = _stackctl.ROOT / "quwoquan_ops/portal"
    vite_binary = portal_dir / "node_modules/.bin/vite"
    deploy_work_root = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    bases = _stackctl.get_target(topology, target_name).get("publicBases") or {}

    def _base(role: str) -> str:
        # 本地 target 的 publicBases 是渲染后的 URL 字符串（含端口）。
        return str(bases.get(role) or "")

    if vite_binary.is_file() and deploy_work_root:
        build_env = {
            **os.environ,
            "QWQ_DEPLOY_TARGET": target_name,
            "VITE_PRODUCT_OPS_BASE_URL": _base("productOps"),
            "VITE_PLATFORM_OPS_BASE_URL": _base("productOps"),
            "VITE_CONTENT_SERVICE_BASE_URL": _base("api"),
            "VITE_ENTITY_SERVICE_BASE_URL": _base("api"),
        }
        try:
            result = subprocess.run(
                [str(vite_binary), "build"],
                cwd=portal_dir,
                env=build_env,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            build_output = (
                Path(deploy_work_root) / target_name / "build" / "ops-portal"
            )
            if result.returncode == 0 and (build_output / "index.html").is_file():
                shutil.copytree(build_output, portal_root, dirs_exist_ok=True)
                return "built"
        except (OSError, subprocess.TimeoutExpired):
            pass
    (portal_root / "index.html").write_text(PORTAL_NOT_BUILT_PAGE, encoding="utf-8")
    return "placeholder"
