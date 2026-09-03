#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from quwoquan_ops.cli.lib.port_manifest import (
    HOST_PORT_VARIABLES_KEY,
    REQUIRED_PROFILES,
    UNOWNED_COMPOSE_SOURCES_KEY,
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
    validate_port_manifest,
)
from quwoquan_ops.cli.lib.service_core_composition import project_compose_document
from quwoquan_ops.cli.print_local_port_profile import ENV_EXPORTS

# 本地 target runtime 闭包里会被 Compose 合并的每一份声明。prod 平面的 Compose
# 由 prod 渲染器拥有，端口不派生自本 manifest，故不在本闭包内。
#
# 每个来源目录都用 `*compose.yaml` 而非精确 `compose.yaml`：只有部分目录放宽时，另一些
# 目录里新增的别名 compose（如 `local-elasticsearch.compose.yaml` 那种命名）会静默逃出
# 闭包，而逃出的表现恰好是「门禁通过」。
LOCAL_COMPOSE_GLOBS = (
    "quwoquan_ops/external/*/deploy/*compose.yaml",
    "quwoquan_service/control-plane/*/deploy/*compose.yaml",
    "quwoquan_service/services/*/deploy/*compose.yaml",
    "quwoquan_service/services/*/environments/*/deploy/*compose.yaml",
)
# 每个来源目录都要做「未裁决即判否」，否则新增文件只需落在没有该检查的目录里就能逃出闭包。
COMPOSE_SOURCE_ROOTS = (
    "quwoquan_ops/external/*/deploy",
    "quwoquan_service/control-plane/*/deploy",
    "quwoquan_service/services/*/deploy",
    "quwoquan_service/services/*/environments/*/deploy",
)
LOCAL_ENVIRONMENT_COMPOSE = (
    "docker-compose.gamma-local.yaml",
    "docker-compose.beta-backing.yaml",
    "docker-compose.local-content-backing.yaml",
)

# `"<host>:<container>[/protocol]"`：host 段可能整段是 `${VAR:-default}` 或
# `${VAR:?msg}`，两者都含冒号，所以 host 用贪婪匹配把分隔位交给最后一个冒号；
# container 段可以是字面端口，也可以是与 host 同源的变量（容器口跟随 canonical 主机口）。
_SHORT_PORT = re.compile(
    r"^(?P<host>.+):(?P<container>\d+|\$\{[^}]*\})(?:/(?P<protocol>[A-Za-z]+))?$"
)
_ENV_DEFAULT = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:-(?P<default>[^}]*)\}$")
_ENV_VARIABLE = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:[:?][^}]*)?\}$")


def _local_compose_sources(
    issues: list[str],
    *,
    unowned_sources: Mapping[str, str],
) -> list[Path]:
    paths: set[Path] = set()
    for pattern in LOCAL_COMPOSE_GLOBS:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    environment_root = ROOT / "quwoquan_ops" / "environments" / "compose"
    adjudicated = (
        set(LOCAL_ENVIRONMENT_COMPOSE) | set(unowned_sources)
    )
    # 这里的 glob 必须与其余来源目录同宽（`*compose*.y*ml`）：只收 `docker-compose*`
    # 前缀时，`local-elasticsearch.compose.yaml` 这种命名既不进 LOCAL_ENVIRONMENT_COMPOSE、
    # 不匹配闭包 glob、也不被本裁决收集 —— 三重漏网，而漏网的表现恰好是「门禁通过」。
    present = {
        path.name
        for path in environment_root.glob("*compose*.y*ml")
        if path.is_file()
    }
    unadjudicated = sorted(present - adjudicated)
    if unadjudicated:
        issues.append(
            "environment Compose file ownership is undeclared: "
            + ", ".join(unadjudicated)
        )
    for name in LOCAL_ENVIRONMENT_COMPOSE:
        path = environment_root / name
        if not path.is_file():
            issues.append(f"declared local environment Compose file is missing: {name}")
            continue
        paths.add(path)
    # 其余来源目录同样要判否未裁决文件：glob 只收 `*compose.yaml`，落在该模式之外的
    # compose 文件（例如 `compose.override.yml`）不会被收进闭包，也就不会被任何断言看到。
    for pattern in COMPOSE_SOURCE_ROOTS:
        for directory in ROOT.glob(pattern):
            if not directory.is_dir():
                continue
            for path in directory.glob("*compose*.y*ml"):
                if not path.is_file() or path in paths:
                    continue
                relative = str(path.relative_to(ROOT))
                # 这里只按仓库相对路径比对：按文件名比对会让 environment 根那两条
                # 「dev 便利栈」豁免在全部来源目录生效 —— 任何服务 deploy 目录下新增
                # 同名 `docker-compose.yaml` 都会被那条无关理由静默豁免。
                if relative in unowned_sources:
                    continue
                issues.append(
                    f"Compose file ownership is undeclared: {relative}"
                )
    return sorted(paths)


def _strip_host_ip_prefix(spec: str) -> str | None:
    """剥掉 `127.0.0.1:` 这类 host_ip 前缀，返回其后的端口段。

    不能按最后一个冒号切分：`127.0.0.1:${VAR:-19210}` 的最后一个冒号在 `${...}`
    内部，切出来的 `-19210}` 既不是字面端口也不是变量，会被判成「无法判定」而静默
    跳过 canonical 断言 —— 一条声称支持的形态反而成了假通过入口。故按括号配对，只在
    `${...}` 之外的冒号上切。
    """
    depth = 0
    for index, character in enumerate(spec):
        if character == "$" and spec[index + 1 : index + 2] == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
        elif character == ":" and not depth:
            return spec[index + 1 :].strip() or None
    return None


def _host_port_variable(spec: str) -> str | None:
    """取出主机端口段引用的 Compose 变量名，供注入声明位反查。"""
    matched = _ENV_VARIABLE.match(spec.strip())
    return matched.group("name") if matched is not None else None


def _host_segment_is_recognized(spec: str) -> bool:
    """host 段是否属于本 gate 能分类的形态。

    「主机端口静态不可判定」有两种成因，判否力度不同：已识别形态但变量不在任何注入
    声明位（如外部 provider 注入面），是有界且登记在案的缺口；而**形态本身没被识别**说明
    gate 连该声明是什么都不知道，此时返回「不可判定」等于把读不出来塌陷成通过 —— 新
    形态一旦出现就静默逃出闭包。故后者必须判否。
    """
    candidate = spec.strip()
    if not candidate:
        return False
    if candidate.isdigit():
        return True
    default = _ENV_DEFAULT.match(candidate)
    if default is not None:
        # `${VAR:-<非数字>}`（含空缺省 `${VAR:-}`）不是「注入决定端口」而是「缺省值本身
        # 不是端口」：变量缺席时 Docker 会随机分配主机口，所有权运行期不可判定。缺省值
        # 静态可读，所以这类必须判否，不能降级成只查 role 声明。
        return default.group("default").strip().isdigit()
    if _ENV_VARIABLE.match(candidate) is not None:
        return True
    tail = _strip_host_ip_prefix(candidate)
    if tail is None or tail == candidate:
        return False
    return _host_segment_is_recognized(tail)


def _declared_host_port(host_spec: str) -> int | None:
    """只解析静态可判定的字面主机端口。

    `${VAR:?msg}` 没有缺省值，端口由启动器按 profile 注入，字面上无从判定；这类形态
    改由 `_injected_host_port` 从注入声明位反查，不在这里猜。
    """
    spec = host_spec.strip()
    matched = _ENV_DEFAULT.match(spec)
    if matched is not None:
        default = matched.group("default").strip()
        return int(default) if default.isdigit() else None
    if spec.isdigit():
        return int(spec)
    tail = _strip_host_ip_prefix(spec)
    if tail is None or tail == spec:
        return None
    return _declared_host_port(tail)


def _host_port_variable_name(host_spec: str) -> str | None:
    """取出 host 段引用的 Compose 变量名，允许带 `127.0.0.1:` 前缀。"""
    spec = host_spec.strip()
    name = _host_port_variable(spec)
    if name is not None:
        return name
    tail = _strip_host_ip_prefix(spec)
    if tail is None or tail == spec:
        return None
    return _host_port_variable(tail)


def _injected_host_port_role(
    host_spec: str,
    *,
    host_port_variables: Mapping[str, str],
) -> str | None:
    """按 manifest 的变量声明位反查该 `${VAR:?...}` 主机端口属于哪个 role。

    `:?` 必填形态在字面上判定不出主机端口，注入值由启动面提供。这里刻意**不**把它折算成
    某个 profile 的 canonical 端口：声明段是 profile 无关的（`QWQ_COMPOSE_*` 一族由
    `local_topology_manifest` 按当前 target 注入，同一变量服务全部 profile），折算只能任取
    一个 profile，既不精确、且折算值本身派生自 manifest，比对它等于自证。

    返回 role 名，让调用方去断言一件真正独立的事：**注入到这个发布口的变量，其声明 role
    必须就是该容器端点的归属 role**。两侧分叉时端口能起但归属判错，而那种漂移不会自己暴露。

    声明位取 manifest 的 `composeHostPortVariables` 而不是 `print_local_port_profile`
    的 `ENV_EXPORTS`：后者只覆盖 target runtime profile 的 shell 导出面，
    content-backing 与 provider substitute 注入面都不在其中。
    """
    name = _host_port_variable_name(host_spec)
    if name is None:
        return None
    return host_port_variables.get(name)


def _injection_declaration_agreement_issues(
    host_port_variables: Mapping[str, str],
) -> list[str]:
    """`ENV_EXPORTS` 与 manifest 声明位对同一变量的 role 说法必须一致。

    两者是两个声明位：manifest 供门禁反查 compose 主机端口，`ENV_EXPORTS` 供启动器导出
    shell 变量。任一侧单独改动都会让注入值与 canonical 归属分叉，而分叉在运行期表现为端口
    能起但归属判错。

    只比对**交集**：`ENV_EXPORTS` 覆盖启动器导出的全部变量，其中多数被 Caddyfile 模板与
    服务环境消费，并不出现在 compose 的主机端口位；反过来独立注入面的变量也不在
    `ENV_EXPORTS` 里。要求任一侧全覆盖都会把无关变量拖进判定。
    """
    issues: list[str] = []
    for profile_name, exports in sorted(ENV_EXPORTS.items()):
        for name, role in sorted(exports.items()):
            declared = host_port_variables.get(name)
            if declared is not None and declared != role:
                issues.append(
                    "host port variable role disagrees between ENV_EXPORTS and "
                    f"{HOST_PORT_VARIABLES_KEY}: {profile_name}/{name} "
                    f"({role} vs {declared})"
                )
    return issues


def _published_endpoint(
    raw: object,
    *,
    source: str,
    service: str,
    issues: list[str],
    host_port_variables: Mapping[str, str],
) -> tuple[int | None, str, int | None, str | None] | None:
    """解析一条发布口声明为 `(containerPort, protocol, hostPort, injectedRole)`。

    containerPort 为 `None` 表示容器口写成与主机口同源的变量，即「容器口跟随该 role 的
    canonical 主机口」——manifest 里由 `profileCanonical` 声明同一件事。

    hostPort 与 injectedRole 恰好一个有值：主机端口是字面量（含 `${VAR:-default}` 缺省）
    时给 hostPort，走 `${VAR:?msg}` 必填形态时给该变量声明的 role。两者都取不到即判否。
    """
    where = f"{source}:{service}"
    if isinstance(raw, Mapping):
        target = raw.get("target")
        published = raw.get("published")
        protocol = str(raw.get("protocol") or "tcp").strip().lower()
        if isinstance(target, bool) or not isinstance(target, (int, str)):
            issues.append(f"{where}: published port target is invalid")
            return None
        container_port = (
            int(str(target).strip()) if str(target).strip().isdigit() else None
        )
        host_port = (
            int(str(published).strip())
            if published is not None and str(published).strip().isdigit()
            else None
        )
        injected_role: str | None = None
        if host_port is None:
            if published is None or not _host_segment_is_recognized(str(published)):
                # 与短语法同一判据：形态未被识别时判否，而不是让它落到后面
                # 「注入变量的 role 不拥有该端点」那条消息上 —— 那条会把恢复动作指向
                # 变量声明位，而真正的问题是这条发布口的主机端口写法本身没被识别。
                issues.append(
                    f"{where}: published host port form is unrecognized: {published}"
                )
                return None
            injected_role = _injected_host_port_role(
                str(published),
                host_port_variables=host_port_variables,
            )
            if injected_role is None:
                issues.append(
                    f"{where}: published host port variable is not declared in "
                    f"{HOST_PORT_VARIABLES_KEY}: "
                    f"{_host_port_variable_name(str(published)) or published}"
                )
                return None
        return container_port, protocol, host_port, injected_role
    if not isinstance(raw, str) or not raw.strip():
        issues.append(f"{where}: published port declaration is invalid")
        return None
    matched = _SHORT_PORT.match(raw.strip())
    if matched is None:
        # 没有主机段的 `"18081"` 形态由 Docker 随机分配主机端口，所有权不可判定。
        issues.append(f"{where}: published port has no declared host port: {raw}")
        return None
    protocol = (matched.group("protocol") or "tcp").strip().lower()
    container = matched.group("container")
    host_segment = matched.group("host")
    host_port = _declared_host_port(host_segment)
    injected_role: str | None = None
    if host_port is None:
        if not _host_segment_is_recognized(host_segment):
            issues.append(
                f"{where}: published host port form is unrecognized: {host_segment}"
            )
            return None
        injected_role = _injected_host_port_role(
            host_segment,
            host_port_variables=host_port_variables,
        )
        if injected_role is None:
            # 形态已识别但反查不到声明：主机端口与归属都判定不出，等于该发布口整条逃出
            # 断言。这里判否而不是跳过，让「新增一个注入变量」必须同时登记声明位。
            issues.append(
                f"{where}: published host port variable is not declared in "
                f"{HOST_PORT_VARIABLES_KEY}: "
                f"{_host_port_variable_name(host_segment) or host_segment}"
            )
            return None
    return (
        int(container) if container.isdigit() else None,
        protocol,
        host_port,
        injected_role,
    )


def _compose_reverse_closure_issues(manifest: dict[str, Any]) -> list[str]:
    """Compose→manifest 反向闭包：每个发布口都必须有 manifest role 认领。

    manifest→composition 的正向校验只能证明「声明过的 role 有对应模块」，证明不了
    「Compose 里没有 manifest 不认识的发布口」。缺这一向时，未声明的 publisher 要等
    到第一次 teardown 归因失败才暴露，而那时已经在破坏性路径上。
    """
    issues: list[str] = []
    profile_roles = {
        profile: compose_published_endpoint_roles(manifest, profile)
        for profile in REQUIRED_PROFILES
    }
    profile_closures = {
        profile: compose_publisher_container_role_closure(roles)
        for profile, roles in profile_roles.items()
    }
    host_port_variables = manifest.get(HOST_PORT_VARIABLES_KEY) or {}
    unowned_sources = manifest.get(UNOWNED_COMPOSE_SOURCES_KEY) or {}
    issues.extend(_injection_declaration_agreement_issues(host_port_variables))
    # 声明段的反向闭合：登记了但 compose 里没人用的变量会长期留存且不可见，之后
    # 有人照它改端口归属却不影响任何真实发布口。用过的变量在下面的循环里收集。
    consumed_variables: set[str] = set()

    sources = _local_compose_sources(
        issues,
        unowned_sources=unowned_sources,
    )
    if not sources:
        issues.append("local Compose closure is empty; the reverse closure gate cannot run")
        return issues
    service_roots = {
        path for path in ROOT.glob("quwoquan_service/services/*/deploy/compose.yaml")
    }
    missing_services = sorted(
        str(path.relative_to(ROOT)) for path in service_roots - set(sources)
    )
    if missing_services:
        issues.append(
            "local Compose closure misses first-party services: "
            + ", ".join(missing_services)
        )

    for path in sources:
        source = str(path.relative_to(ROOT))
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            issues.append(f"{source}: Compose source is unreadable: {exc}")
            continue
        if not isinstance(payload, Mapping):
            issues.append(f"{source}: Compose source must be a mapping")
            continue
        try:
            projected = project_compose_document(payload)
        except (TypeError, ValueError) as exc:
            issues.append(f"{source}: service-core projection failed: {exc}")
            continue
        services = projected.get("services")
        if not isinstance(services, Mapping):
            issues.append(f"{source}: Compose services must be a mapping")
            continue
        for service, definition in services.items():
            if not isinstance(definition, Mapping):
                continue
            declared_ports = definition.get("ports")
            if declared_ports is None:
                continue
            if isinstance(declared_ports, (str, bytes, Mapping)) or not isinstance(
                declared_ports, Sequence
            ):
                issues.append(f"{source}:{service}: Compose ports must be a list")
                continue
            for raw in declared_ports:
                if isinstance(raw, str):
                    matched_host = _SHORT_PORT.match(raw.strip())
                    if matched_host is not None:
                        used = _host_port_variable_name(matched_host.group("host"))
                        if used is not None:
                            consumed_variables.add(used)
                elif isinstance(raw, Mapping) and raw.get("published") is not None:
                    used = _host_port_variable_name(str(raw["published"]))
                    if used is not None:
                        consumed_variables.add(used)
                parsed = _published_endpoint(
                    raw,
                    source=source,
                    service=str(service),
                    issues=issues,
                    host_port_variables=host_port_variables,
                )
                if parsed is None:
                    continue
                container_port, protocol, host_port, injected_role = parsed
                name = str(service)
                if container_port is None:
                    # 容器口跟随 canonical 主机口：只有 `profileCanonical` 声明的
                    # publisher 才是这种形态，两侧端口必须同值。
                    follower_identities = [
                        identity
                        for roles in profile_roles.values()
                        for identity in roles
                        if identity[0] == name
                        and identity[2] == protocol
                        and identity[1] == identity[3]
                    ]
                    canonical_followers = {
                        identity[1] for identity in follower_identities
                    }
                    if not canonical_followers:
                        issues.append(
                            f"{source}:{name}: profile-canonical published endpoint has "
                            f"no canonical role: {protocol}"
                        )
                    elif host_port is not None and host_port not in canonical_followers:
                        issues.append(
                            f"{source}:{name}: declared host port is not canonical for "
                            f"profile-canonical {protocol}: {host_port}"
                        )
                    elif injected_role is not None:
                        # 这一形态的主机端口恒非字面量（容器口与主机口同源同变量），
                        # 所以判据只能落在注入变量上：它声明的 role 必须就是该 follower
                        # 端点的归属 role。漏掉这一条时，把变量换成另一个已声明变量
                        # 门禁仍会放行，而运行期会把该服务发布到别的 role 的 canonical 口。
                        follower_roles = {
                            role
                            for roles in profile_roles.values()
                            for identity, role in roles.items()
                            if identity in follower_identities
                        }
                        if injected_role not in follower_roles:
                            issues.append(
                                f"{source}:{name}: injected host port variable role does "
                                f"not own profile-canonical {protocol}: {injected_role} "
                                "not in " + ",".join(sorted(follower_roles))
                            )
                    continue
                identity = (name, container_port, protocol)
                owning_profiles = [
                    profile
                    for profile, closure in profile_closures.items()
                    if identity in closure
                ]
                if not owning_profiles:
                    issues.append(
                        f"{source}:{name}: published endpoint has no canonical role: "
                        f"{container_port}/{protocol}"
                    )
                    continue
                if host_port is None:
                    # 主机端口走 `${VAR:?}` 注入：断言注入变量声明的 role 就是该容器端点
                    # 的归属 role。这是独立判据 —— 折算成 canonical 端口再比对反而是自证，
                    # 因为折算值本身派生自同一份 manifest。
                    owners = {
                        role
                        for profile in owning_profiles
                        for role in profile_closures[profile][identity]
                    }
                    if injected_role not in owners:
                        issues.append(
                            f"{source}:{name}: injected host port variable role does not "
                            f"own {container_port}/{protocol}: {injected_role} not in "
                            + ",".join(sorted(owners))
                        )
                    continue
                if not any(
                    (*identity, host_port) in profile_roles[profile]
                    for profile in owning_profiles
                ):
                    issues.append(
                        f"{source}:{name}: declared host port is not canonical for "
                        f"{container_port}/{protocol}: {host_port}"
                    )

    unused = sorted(set(host_port_variables) - consumed_variables)
    if unused:
        issues.append(
            f"{HOST_PORT_VARIABLES_KEY} declares variables no Compose host port uses: "
            + ", ".join(unused)
        )
    return issues


def main() -> int:
    manifest = load_port_manifest()
    issues = validate_port_manifest(manifest)
    if "fixture-gateway" in manifest.get("roles", {}):
        issues.append("retired environment role fixture-gateway must not be canonical")
    if not issues:
        issues.extend(_compose_reverse_closure_issues(manifest))
    if issues:
        print("[verify_local_env_port_manifest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    preview = {
        profile: profile_ports(manifest, profile)
        for profile in ("alpha-local", "beta-local", "gamma-local", "prod-sim")
    }
    print("[verify_local_env_port_manifest] OK")
    print(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
