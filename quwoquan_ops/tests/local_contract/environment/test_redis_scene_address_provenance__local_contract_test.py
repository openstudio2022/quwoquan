#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003.t1
"""锁定 Redis scene 的地址来源在四环境成套：装配期判否不再推迟到部署时暴露。

骨架按 DEC-028 对「声明与地址不成套」的 scene 在装配期判否，`mode: memory` 是唯一
合法的关停声明。判否是正确的暴露方式，但暴露点在实跑该档位时——本门禁把它提前到
提交时：每个服务每个被消费的 scene 在每个环境必须能指出一处地址来源，否则该档位
启动即失败。

判定消费四层取值后的渲染快照而不是服务快照原文，因为 `mode` 可以由跨服务默认层
（quwoquan_ops/environments/config-defaults.yaml）提供而根本不出现在服务文件里。
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.render_runtime_config import render_workload  # noqa: E402

SERVICE_ROOT = ROOT / "quwoquan_service" / "services"
PROD_PLANE_RENDERER = Path("quwoquan_ops/cli/prod/render_prod_plane_stack.py")

# 注入源按环境分组。非 prod 三档共用服务 compose 作为容器编排基线，各自再叠一个
# 启动器；prod 由专用渲染器注入。不分组会让某一档的注入替另一档背书——circle 的
# prod 就曾靠 compose 里的键假通过。
LAUNCHERS_BY_ENVIRONMENT = {
    "alpha": (Path("quwoquan_ops/cli/alpha/content_release_runtime.py"),),
    "beta": (Path("quwoquan_app/scripts/tools/device/beta_manual_app.sh"),),
    "gamma": (Path("quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"),),
    "prod": (PROD_PLANE_RENDERER,),
}
ENVIRONMENTS = tuple(LAUNCHERS_BY_ENVIRONMENT)

SHARED_ADDR_FIELD = re.compile(r'`yaml:"-" env:"(REDIS_ADDR)"')
PROD_PLANE_SERVICE = re.compile(r'name == "([a-z0-9-]+)"')
# 装配点：Go 侧 scene 集合的真相源是 RedisScenes 钩子返回的 map 键，不是 config
# struct 的字段。struct 里声明而钩子不返回的 scene 不会被装配（integration 的
# rec 就是如此），要求它有地址会把判否指向错误的修复位置。
SCENE_TYPE_ALIAS = re.compile(r"type (\w+) = (?:\w+\.)?RedisSceneConfig\b")
SCENE_MAP_KEY = re.compile(r'"([a-z0-9_]+)":')
# prod plane 的两种注入写法：字面量键根，以及 `for scene in (...)` 循环里的
# f-string 拼接。只认字面量会把循环注入误报为缺失。
PROD_PLANE_LITERAL = re.compile(r'_wire_redis_scene\(\s*environment,\s*"([A-Z0-9_]+)"')
PROD_PLANE_LOOP = re.compile(
    r'for scene in \(([^)]*)\):\s*\n\s*_wire_redis_scene\(\s*environment,\s*f"([A-Z0-9_]+)_\{scene\}"'
)


def service_prefix(service: str) -> str:
    """服务 env 前缀，与 servicekit.DefaultEnvPrefix 同构。"""
    return service.removesuffix("-service").replace("-", "_").upper()


def production_go_sources(service: str) -> list[str]:
    """本服务全部非测试 Go 源码。scene 的消费点可能在 cmd/ 也可能在 internal/。"""
    return [
        path.read_text(encoding="utf-8")
        for path in sorted((SERVICE_ROOT / service).rglob("*.go"))
        if not path.name.endswith("_test.go")
    ]


def prod_plane_services() -> set[str]:
    """prod plane 渲染器覆盖的服务名。

    不在其中的服务（circle-service、api-edge）不由 prod plane 部署，它们的 prod
    地址注入归属在云上 k8s，仓内没有可判定的注入源，由 spec.md 的 OPEN-014 承接。
    对它们跳过 prod 判定是显式的判据边界，不是豁免——一旦迁入 prod plane 就自动
    纳入判定。
    """
    source = (ROOT / PROD_PLANE_RENDERER).read_text(encoding="utf-8")
    return set(PROD_PLANE_SERVICE.findall(source))


def shared_address_keys(service: str, sources: list[str]) -> list[str]:
    """本服务声明的跨 scene 共享地址位。

    一个显式声明位为多个 scene 的同一字段供值，与全局默认层的 `redis.*.mode`
    同构（DEC-028）；它是合法的地址来源，只找完整 scene 键名会把它误报为缺失。
    """
    keys: set[str] = set()
    for source in sources:
        keys.update(SHARED_ADDR_FIELD.findall(source))
    return sorted(keys)


def assembled_scenes(sources: list[str]) -> set[str]:
    """服务实际装配的 scene 集合。

    真相源有两种，按优先级取：声明了 `RedisScenes` 钩子的服务以钩子返回的 map 键
    为准，未声明钩子的服务由骨架从 config struct 的 scene 字段自动发现（DEC-028
    的「声明即装配」）。两者都要支持——只认钩子会让一半服务以「跳过」的形式假绿。

    以钩子优先而不是取两者并集，是因为 struct 里声明而钩子不返回的 scene 不会被
    装配（integration 的 rec 就是如此），要求它有地址会把判否指向错误的修复位置：
    它该从 schema 里删掉，而不是被注入。
    """
    # scene 配置类型可以用别名声明（content 的 redisSceneCfg），只匹配全名会漏掉
    # 整个服务，而漏掉的服务会以「跳过」的形式假绿。
    aliases = {"RedisSceneConfig"}
    for source in sources:
        aliases.update(SCENE_TYPE_ALIAS.findall(source))
    alternation = "|".join(sorted(map(re.escape, aliases)))
    block_pattern = re.compile(
        r"map\[string\](?:\w+\.)?(?:" + alternation + r")\{(.*?)\n\t*\}", re.DOTALL
    )
    hook_scenes: set[str] = set()
    for source in sources:
        for block in block_pattern.findall(source):
            hook_scenes.update(SCENE_MAP_KEY.findall(block))
    if hook_scenes:
        return hook_scenes

    field_pattern = re.compile(
        r"(?:\w+\.)?(?:" + alternation + r')\s+`yaml:"([a-z0-9_]+)"'
    )
    struct_scenes: set[str] = set()
    for source in sources:
        struct_scenes.update(field_pattern.findall(source))
    return struct_scenes


def prod_plane_scene_key_roots(service: str) -> set[str]:
    """prod plane 为该服务注入的 scene 键根，按 `if name == "<service>":` 分块解析。"""
    source = (ROOT / PROD_PLANE_RENDERER).read_text(encoding="utf-8")
    blocks = list(re.finditer(rf'if name == "{re.escape(service)}":', source))
    if not blocks:
        return set()
    boundaries = [match.start() for match in re.finditer(r'if name == "', source)]
    roots: set[str] = set()
    for block in blocks:
        end = next((b for b in boundaries if b > block.start()), len(source))
        body = source[block.start():end]
        roots.update(PROD_PLANE_LITERAL.findall(body))
        for scenes, prefix in PROD_PLANE_LOOP.findall(body):
            for scene in re.findall(r'"([A-Z0-9_]+)"', scenes):
                roots.add(f"{prefix}_{scene}")
    return roots


def address_source(
    service: str,
    scene: str,
    environment: str,
    compose: str,
    shared_keys: list[str],
) -> str | None:
    """找出该 scene 在该环境的地址注入来源，找不到返回 None。

    三种命中形态：完整键名、helper 拼接的键根（prod plane 的 `_wire_redis_scene`
    只在字面量里留下 `"PFX_REDIS_SCENE"`）、本服务声明的共享地址位。
    """
    prefix = service_prefix(service)
    if environment == "prod":
        key_root = f"{prefix}_REDIS_{scene.upper()}"
        roots = prod_plane_scene_key_roots(service)
        if key_root in roots:
            return PROD_PLANE_RENDERER.name
        if any(f"{prefix}_{key}".removesuffix("_ADDR") in roots for key in shared_keys):
            return PROD_PLANE_RENDERER.name
        source = (ROOT / PROD_PLANE_RENDERER).read_text(encoding="utf-8")
        if any(re.search(rf"\b{prefix}_{key}\b", source) for key in shared_keys):
            return PROD_PLANE_RENDERER.name
        return None
    patterns = [rf"\b{prefix}_REDIS_{scene.upper()}_ADDRS?\b"]
    patterns += [rf"\b{prefix}_{key}\b" for key in shared_keys]
    candidates = [
        (path.name, (ROOT / path).read_text(encoding="utf-8"))
        for path in LAUNCHERS_BY_ENVIRONMENT[environment]
    ]
    candidates.append(("compose.yaml", compose))
    for name, text in candidates:
        if any(re.search(pattern, text) for pattern in patterns):
            return name
    return None


def rendered_scenes(service: str, environment: str) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as work:
        output = Path(work) / f"{service}.yaml"
        render_workload(ROOT, environment, service, output)
        document = yaml.safe_load(output.read_text(encoding="utf-8")) or {}
    return document.get("redis") or {}


def redis_bearing_services() -> list[str]:
    """渲染快照里带 redis 段的服务。取快照而不是 struct 字段：scene 可以用类型
    别名声明，也可以声明在 internal/ 下，静态匹配类型名会漏检。"""
    services = []
    for entry in sorted(SERVICE_ROOT.iterdir()):
        if not entry.is_dir() or not (entry / "config" / "schema.yaml").is_file():
            continue
        try:
            if rendered_scenes(entry.name, "alpha"):
                services.append(entry.name)
        except Exception:  # noqa: BLE001 - 渲染失败由该服务自己的门禁负责
            continue
    return services


@pytest.mark.parametrize("service", redis_bearing_services())
def test_every_consumed_redis_scene_has_an_address_provenance__local_contract(
    service: str,
) -> None:
    sources = production_go_sources(service)
    assembled = assembled_scenes(sources)
    if not assembled:
        # 两种合法情形：非 Go 服务（recommendation-service），以及刻意不装配任何
        # scene 的服务（api-edge 不持有领域缓存）。两者都没有可判定的 scene。
        pytest.skip(f"{service} assembles no Redis scene")
    compose_path = SERVICE_ROOT / service / "deploy" / "compose.yaml"
    compose = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
    shared_keys = shared_address_keys(service, sources)
    prod_plane = prod_plane_services()

    gaps: list[str] = []
    for environment in ENVIRONMENTS:
        if environment == "prod" and service not in prod_plane:
            continue
        rendered = rendered_scenes(service, environment)
        consumed = [scene for scene in sorted(rendered) if scene in assembled]
        with_address = {
            scene
            for scene in consumed
            if str(rendered[scene].get("addr") or "").strip()
            or rendered[scene].get("addrs")
            or address_source(service, scene, environment, compose, shared_keys)
        }
        for scene in consumed:
            config = rendered[scene]
            mode = str(config.get("mode") or "").strip()
            if mode not in {"memory", "standalone", "cluster"}:
                gaps.append(
                    f"{environment}/{scene} has no valid explicit mode "
                    f"(got {mode or '<unset>'}); declare memory, standalone or cluster "
                    "in the service environment config, environment defaults or global defaults"
                )
                continue
            if mode == "memory" or scene in with_address:
                continue
            # 整段缺席的 scene 复用另一段的完整声明（DEC-028 的唯一合法复用
            # 规则），复用源必然是同服务的另一个 scene，因此只要本服务在该环境
            # 有任一 scene 能指出地址来源，复用后的这一段就不缺地址。
            if not any(config.get(field) for field in ("mode", "addr", "addrs", "db", "tls")):
                if with_address:
                    continue
            gaps.append(
                f"{environment}/{scene} (mode={mode or '<unset>'}) has no snapshot "
                f"address, no injection source for this environment and no "
                f"explicit mode: memory"
            )
    assert not gaps, (
        f"{service}: these Redis scenes fail closed at startup in the listed "
        f"environments; inject the scene address for that environment or declare "
        f"mode: memory: {gaps}"
    )
