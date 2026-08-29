"""prod plane 的 Redis 物理组网降档必须显式注入。

环境快照里的 `redis.<scene>.mode: cluster` / `tls: true` 描述的是云上 prod 的
物理组网。prod plane（自托管 onebox 形态）的 Redis 是**明文单点**，因此每个声明
了 cluster 的 scene 都必须在 prod plane 上被显式降档，否则会落进两个都没有运行
期信号的失效：

- 单点地址被当成 cluster 种子：`addrs` 为空，服务按 servicekit 的装配期判据
  直接启动失败（修复前是静默回落进程内存，多副本各持一份不共享、重启即丢的
  「Redis」）。
- 按 TLS 握手连明文端口：连接超时表现为依赖不可用，而不是配置错误。

本门禁对每个服务实跑 prod plane 渲染器的服务改写段，把渲染出的 environment 与
该服务 prod 快照里的 scene 声明对账。判据只有一条：声明与注入必须能拼出一个
在 prod plane 上真实可连的组网。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as renderer


ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = ROOT / "quwoquan_service"

# recommendation-service 是 Python 服务，不经 servicekit 装配 Redis，其 scene
# 声明由自身运行时消费，不适用本门禁的注入判据。
NON_SERVICEKIT_SERVICES = {"recommendation-service"}


def _environment_token(name: str) -> str:
    """与 servicekit.DefaultEnvPrefix 同构：去 -service 后缀后大写、连字符转下划线。"""
    trimmed = name.removesuffix("-service")
    return re.sub(r"[^A-Z0-9]+", "_", trimmed.upper()).strip("_")


def _service_dirs() -> list[Path]:
    dirs = sorted((SERVICE_ROOT / "services").iterdir())
    platform_ops = SERVICE_ROOT / "control-plane/platform-ops"
    if platform_ops.exists():
        dirs.append(platform_ops)
    return [d for d in dirs if d.is_dir()]


def _declared_scenes(service_dir: Path) -> dict[str, dict[str, object]]:
    """从 prod 快照的 overrides 里取出该服务声明的 redis scene 段。"""
    config_path = service_dir / "environments/prod/config.yaml"
    if not config_path.exists():
        return {}
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    overrides = document.get("overrides") or {}
    prefix = f"sys.{service_dir.name}.redis."
    scenes: dict[str, dict[str, object]] = {}
    for key, value in overrides.items():
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix) :]
        parts = remainder.split(".")
        # 只取 scene 直属字段（mode/addr/addrs/tls），pool.* 等嵌套段不参与判据。
        if len(parts) != 2:
            continue
        scenes.setdefault(parts[0], {})[parts[1]] = value
    return scenes


def _rendered_environment(service_dir: Path) -> dict[str, str]:
    """实跑 prod plane 的服务改写段，取该服务最终注入的 environment。"""
    compose_path = service_dir / "deploy/compose.yaml"
    if not compose_path.exists():
        return {}
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    service_spec = (compose.get("services") or {}).get(service_dir.name)
    if not isinstance(service_spec, dict):
        return {}
    rendered = renderer._rewrite_service(
        service_dir.name,
        service_spec,
        {service_dir.name, "mongodb", "redis", "postgres"},
        image_version="sha256-image",
        config_version="sha256-config",
        versioned_image=False,
        instance="prevalidate",
        replica_id="r0",
        config_root="runtime/config-root",
        media_root="runtime/media",
        legal_root="runtime/legal",
        portal_root="runtime/portal",
        web_root="runtime/web",
        caddyfile_path="runtime/Caddyfile",
        model_cache_root="runtime/model-cache",
        # hosted 是 prod plane 的默认数据面形态：数据主机在栈外，因此每个数据面
        # 地址都必须被显式注入，不能靠 compose 基线里的 isolated 服务名兜底。
        data_mode="hosted",
        startup_services={service_dir.name},
    )
    environment = rendered.get("environment")
    return environment if isinstance(environment, dict) else {}


def _is_unrendered_placeholder(value: object) -> bool:
    return isinstance(value, str) and value.strip().startswith("${")


class ProdPlaneRedisTopologyDowngradeTest(unittest.TestCase):
    def test_cluster_scenes_are_downgraded_or_seeded_on_the_prod_plane(self) -> None:
        for service_dir in _service_dirs():
            if service_dir.name in NON_SERVICEKIT_SERVICES:
                continue
            scenes = _declared_scenes(service_dir)
            if not scenes:
                continue
            environment = _rendered_environment(service_dir)
            if not environment:
                continue
            token = _environment_token(service_dir.name)
            for scene, fields in sorted(scenes.items()):
                with self.subTest(service=service_dir.name, scene=scene):
                    key_root = f"{token}_REDIS_{scene.upper()}"
                    mode = str(fields.get("mode") or "").strip().lower()
                    if mode != "cluster":
                        continue
                    # 快照自带集群种子的 scene 声明是自足的：物理组网已经完整，
                    # 种子主机在本平面是否可达属于地址可达性，不是注入完整性。
                    if fields.get("addrs"):
                        continue
                    injected_mode = environment.get(f"{key_root}_MODE")
                    injected_addrs = environment.get(f"{key_root}_ADDRS")
                    self.assertTrue(
                        injected_mode or injected_addrs,
                        f"{service_dir.name} redis.{scene} 快照声明 mode=cluster，"
                        f"prod plane 必须注入 {key_root}_MODE 降档为单点，或注入 "
                        f"{key_root}_ADDRS 给出集群种子；两者都缺时 servicekit 在"
                        "装配期判否，服务起不来。",
                    )
                    if injected_mode:
                        self.assertEqual(
                            str(injected_mode).strip().lower(),
                            "standalone",
                            f"{service_dir.name} redis.{scene} 在 prod plane 上"
                            f"只能降档为 standalone，实际注入 {injected_mode!r}。",
                        )

    def test_tls_scenes_are_downgraded_for_the_plaintext_single_node_redis(self) -> None:
        for service_dir in _service_dirs():
            if service_dir.name in NON_SERVICEKIT_SERVICES:
                continue
            scenes = _declared_scenes(service_dir)
            if not scenes:
                continue
            environment = _rendered_environment(service_dir)
            if not environment:
                continue
            token = _environment_token(service_dir.name)
            for scene, fields in sorted(scenes.items()):
                with self.subTest(service=service_dir.name, scene=scene):
                    if fields.get("tls") is not True:
                        continue
                    key_root = f"{token}_REDIS_{scene.upper()}"
                    # 带集群种子的 scene 连的是真 TLS 集群，不需要降档。种子既
                    # 可能来自快照声明，也可能来自本平面注入。
                    if fields.get("addrs") or environment.get(f"{key_root}_ADDRS"):
                        continue
                    injected_tls = environment.get(f"{key_root}_TLS")
                    self.assertIsNotNone(
                        injected_tls,
                        f"{service_dir.name} redis.{scene} 快照声明 tls=true，"
                        f"prod plane 的 Redis 是明文单点，必须注入 {key_root}_TLS"
                        "=false，否则 TLS 握手连明文端口只表现为依赖超时。",
                    )
                    self.assertEqual(
                        str(injected_tls).strip().lower(),
                        "false",
                        f"{service_dir.name} redis.{scene} 在 prod plane 上必须"
                        f"按明文连接，实际注入 {injected_tls!r}。",
                    )

    def test_scene_addresses_are_injected_rather_than_left_as_placeholders(self) -> None:
        """快照里的 `${KEY}` 占位符必须由 prod plane 注入同名键兑现。

        未兑现的占位符会作为字面量流到运行期：地址解析失败或连到一个名叫
        `${KEY}` 的主机，两者都不是配置错误的形状。
        """
        for service_dir in _service_dirs():
            if service_dir.name in NON_SERVICEKIT_SERVICES:
                continue
            scenes = _declared_scenes(service_dir)
            if not scenes:
                continue
            environment = _rendered_environment(service_dir)
            if not environment:
                continue
            for scene, fields in sorted(scenes.items()):
                addr = fields.get("addr")
                if not _is_unrendered_placeholder(addr):
                    continue
                referenced = str(addr).strip()[2:-1].split(":")[0]
                with self.subTest(service=service_dir.name, scene=scene):
                    self.assertIn(
                        referenced,
                        environment,
                        f"{service_dir.name} redis.{scene} 的 addr 是占位符 "
                        f"{addr!r}，但 prod plane 未注入 {referenced}。",
                    )


if __name__ == "__main__":
    unittest.main()
