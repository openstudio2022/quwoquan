"""规则标识、真相源路径、层规则与命名表（W5 同源声明的载体）。"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# 规则标识与真相源路径
# ---------------------------------------------------------------------------

RULE_ID = "object-path-map/v2"

CONTRACT_GRAPH_PATH = Path("quwoquan_service/generated/contract_graph.json")
PAGE_OBJECT_CONTRACT_PATH = Path(
    "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"
)
SERVICE_ROOT_GLOBS = (
    "quwoquan_service/services/*",
    "quwoquan_service/control-plane/*",
)
APP_ROOT = Path("quwoquan_app")
APP_LIB_ROOT = APP_ROOT / "lib"
APP_TEST_ROOT = APP_ROOT / "test"
APP_SOURCE_SUFFIX = ".dart"
CLOUD_SOURCE_SUFFIXES = frozenset({".go", ".py"})
CLOUD_TEST_LAYERS = ("local_contract", "api_integration")

#: 云侧 `tests/support/**` 是服务内共享测试支撑根，不承载对象身份，
#: 与 verify_service_architecture.py 只校验 local_contract / api_integration 一致。
CLOUD_TEST_SUPPORT_ROOT = "support"
APP_TEST_LAYERS = ("local_contract", "api_integration", "user_acceptance", "support")

#: 非对象测试身份来自测试树的物理语义，而不是人工清单。它们不承载某个
#: business object 的三层测试证据：runtime/design_system 是横切能力，journeys
#: 是跨对象结果，Patrol 目录只是 runner shell。
APP_CROSS_OBJECT_JOURNEY_ROOT = "journeys"
APP_CROSS_OBJECT_JOURNEY_TEST_LAYERS = frozenset(
    {"local_contract", "user_acceptance"}
)
APP_PATROL_RUNNER_ROOT = "patrol"
APP_PATROL_RUNNER_LAYER = "user_acceptance"
APP_PATROL_RUNNER_FILES = frozenset({"patrol_test_main.dart", "test_bundle.dart"})
APP_TEST_NON_OBJECT_IDENTITY_METHOD = "test_non_object_identity"

OUTPUT_DIR_NAME = "object-path-map"

# ---------------------------------------------------------------------------
# 层名与 kind 感知的必需层规则（W5 evidence loader 的同源依据）
# ---------------------------------------------------------------------------

#: 云侧 DDD 层，与 verify_service_architecture.py 的 ``LAYERS`` 同名同义。
CLOUD_LAYERS = ("domain", "application", "adapters", "infrastructure")

#: 端侧业务对象统一位于 ``lib/service/<service>/<context>/<object>/<layer>/``。
#: ``service`` 是容器段，具体 service 名由服务 ``contracts/domain.yaml`` 与 context
#: 目录共同派生；端侧不再把 domain 复制为 lib 顶层目录。
APP_SERVICE_ROOT_SEGMENT = "service"

#: 端侧目标层，对应
#: ``quwoquan_app/lib/service/<service>/<context>/<object>/<layer>/``。
APP_LAYERS = ("domain", "application", "adapters", "presentation")

#: 端云层名等价映射：端侧 presentation 承担云侧入向 adapters，端侧 adapters 承担
#: 云侧出向 infrastructure。端侧不存在独立的出向/入向拆分目录。
APP_TO_CLOUD_LAYER_EQUIVALENCE = {
    "domain": "domain",
    "application": "application",
    "presentation": "adapters/inbound",
    "adapters": "infrastructure",
}

#: 云侧 kind → 必需层。verify_service_architecture.py 中
#: ``verify_kind_aware_object_implementation`` 的 ``required_layers`` 镜像，
#: 由 ``check_cloud_layer_rule_mirror`` 每次运行时 AST 比对防漂移。
REQUIRED_CLOUD_LAYERS_BY_KIND = {
    "aggregate_root": ("application", "domain", "infrastructure"),
    "append_only_fact": ("application", "domain", "infrastructure"),
    # 长流程编排器（saga）三层缺一不可：domain 放状态机与补偿规则，application 放
    # 编排，infrastructure 放 checkpoint 持久化。
    "process_manager": ("application", "domain", "infrastructure"),
    "projection": ("application", "infrastructure"),
    "runtime_session": ("application", "domain", "infrastructure"),
}

#: 云侧 external_reference 不在上表内：它要求 application，且 adapters 与
#: infrastructure 至少命中一个（同 verify_service_architecture.py）。
CLOUD_EXTERNAL_REFERENCE_REQUIRED = ("application",)
CLOUD_EXTERNAL_REFERENCE_EITHER = ("adapters", "infrastructure")

#: App 必需层不能由云侧 object kind 推断。只有 ContractGraph 中真实存在
#: ``clientContract`` 的 operation 才证明 App 消费该对象，并要求端侧用例编排与
#: Remote adapter；纯云对象不得因为是 aggregate/runtime_session 就被强制造空层。
APP_OPERATION_REQUIRED_LAYERS = ("application", "adapters")

#: 页面物理 owner 由 canonical ``source_path`` 的对象形态反推。页面参与对象只经
#: 公开 application port 被组合，不自动拥有 presentation。
APP_PAGE_OWNER_REQUIRED_LAYERS = ("application", "presentation")

#: domain 只在所属规格明确声明端侧不变式/状态机时成立；云侧 kind、operation 的
#: invariantTarget 或一个物理目录都不能替端侧猜测能力。
APP_CLIENT_INVARIANT_REQUIRED_LAYERS = ("domain",)

#: 端侧禁止层：由云侧 object kind 的写面语义派生，`kind` 是唯一输入。
#:
#: * ``append_only_fact`` 不得拥有 presentation（事实流不直接成页）。
#: * ``runtime_session`` 不得拥有 presentation：session 只在连接/请求期间存在，
#:   不是持久业务聚合（见 ``realtime/connection/object.yaml``）。需要展示会话状态
#:   时，由某个业务对象的 presentation 消费 session 的公开 query port，而不是让
#:   session 自己成页。``runtime_session`` 同时禁止 PageOwned，该判据由
#:   ``verify_app_client_contract_kind_alignment.py`` 的 ``runtime_session_app_shape``
#:   按 ``PRESENTATION_REQUIREMENT_SOURCE`` 求值。
#: * ``external_reference`` 不得拥有 domain 与 presentation：它没有端侧不变式
#:   （刷新语义是 provider read-through without local authoritative state），也不
#:   拥有页面；展示外部引用的页面归发起它的业务对象。
#:
#: ``projection`` 不进此表：projection 合法拥有 presentation（读模型页，如
#: ``chat.chat_inbox_view`` 的会话列表页、``search.search_index_view`` 的搜索页），
#: 用禁止层表达会把真实形态判成违规。它的 kind 义务是「端侧没有写面、没有本地可变
#: patch 路径」，由 ``verify_app_client_contract_kind_alignment.py`` 的
#: ``projection_local_mutation_path`` 求值。
#:
#: ``process_manager`` 不进此表：它通常不是 PageOwned（长流程由发起它的页面组合，
#: 自身不拥有页面），但 ``assistant.assistant_run`` 这类"流程即体验主线"的对象
#: 确实拥有 presentation，禁止层会把真实形态判成违规。是否 PageOwned 仍由
#: ``PAGE_OBJECT_CONTRACT_PATH#pages[*].source_path`` 这一唯一权威信号决定。
FORBIDDEN_APP_LAYERS_BY_KIND = {
    "append_only_fact": ("presentation",),
    "external_reference": ("domain", "presentation"),
    "runtime_session": ("presentation",),
}

#: 端侧 process port 命名规范（``process_manager`` 专用）。
#:
#: 长流程的端侧读写面必须与聚合读写面分开命名：状态/进度读取用 ``*ProcessQuery``，
#: 推进/取消/恢复用 ``*ProcessCommandWriter``。禁止让流程状态更新复用聚合的
#: ``*CommandWriter``——两者的失败语义不同（聚合命令要么成功要么失败，流程命令只是
#: 向状态机投递一次推进意图，真实终态要回读 checkpoint），共用一个 port 会让调用方
#: 无法区分"命令已受理"与"流程已完成"。
#:
#: 这里只登记规范本身并随 ``layerRules`` 输出，不在本文件内扫描端侧标识符：端侧
#: port 改名会穿透 ``quwoquan_app/lib/runtime/di/**`` 与 generated client，属于独立
#: 的端侧迁移工序。
APP_PROCESS_PORT_NAMING = {
    "query": "*ProcessQuery",
    "commandWriter": "*ProcessCommandWriter",
    "forbiddenSharedWithAggregate": "*CommandWriter",
}

#: 端侧 append port 命名规范（``append_only_fact`` 专用）。
#:
#: 事实只追加、不更新（``access.commands: append_only_sink``、
#: ``lifecycle.immutable: true``），因此它的端侧写面必须与聚合写面**类型上可区分**：
#: 聚合命令改变聚合状态，追加只是投递一条不可变事实。共用 ``*CommandWriter`` 会让
#: 调用方以为可以 update 一条已追加的事实。
#:
#: 实际扫描由 ``verify_app_client_contract_kind_alignment.py`` 的
#: ``append_only_fact_append_port_shape`` 承担；本文件只登记规范并随 ``layerRules``
#: 输出，保持派生器与门禁同源。
APP_APPEND_PORT_NAMING = {
    "appender": "*FactAppender",
    "query": "*FactQuery",
    "forbiddenSharedWithAggregate": "*CommandWriter",
}

#: 端侧 session port 命名规范（``runtime_session`` 专用）。
#:
#: session 的写面是会话生命周期（``access.commands: session_facade``），不是聚合命令；
#: 它不拥有 presentation、不成页，禁止层见 ``FORBIDDEN_APP_LAYERS_BY_KIND``。
APP_SESSION_PORT_NAMING = {
    "facade": "*SessionFacade",
    "query": "*SessionQuery",
    "forbiddenLayers": ("presentation",),
    "forbiddenPageOwnership": True,
}

#: 三类端侧层义务的各自唯一来源。
APP_OPERATION_REQUIREMENT_SOURCE = f"{CONTRACT_GRAPH_PATH.as_posix()}#operations[*].clientContract"
PRESENTATION_REQUIREMENT_SOURCE = f"{PAGE_OBJECT_CONTRACT_PATH.as_posix()}#pages[*].source_path"
CLIENT_INVARIANT_REQUIREMENT_SOURCE = (
    "object-owned feature-tree REQ/GWT; never inferred from a directory"
)


def required_cloud_layers(kind: str) -> tuple[str, ...]:
    """返回云侧 *kind* 的必需层（external_reference 的 either 组合另行判定）。"""
    return REQUIRED_CLOUD_LAYERS_BY_KIND.get(kind, ())


def required_app_layers(
    *,
    has_client_contract_operation: bool,
    owns_page: bool,
    has_client_invariant: bool,
) -> tuple[str, ...]:
    """按真实端侧能力返回必需层，不从云侧 object kind 猜 App 实现。

    - App operation：``application + adapters``；
    - 页面物理 owner：``application + presentation``；
    - 所属规格明确声明的端侧不变式/状态机：``domain``。
    """
    layers: list[str] = []
    if has_client_contract_operation:
        layers.extend(APP_OPERATION_REQUIRED_LAYERS)
    if owns_page:
        layers.extend(APP_PAGE_OWNER_REQUIRED_LAYERS)
    if has_client_invariant:
        layers.extend(APP_CLIENT_INVARIANT_REQUIRED_LAYERS)
    return tuple(sorted(set(layers)))


# ---------------------------------------------------------------------------
# 端侧现状路径 → 层角色的派生规则
# ---------------------------------------------------------------------------

#: 端侧目标形态的固定位置。**一旦文件搬到目标形态，身份就与云侧一样可由物理位置
#: 精确反推，任何启发式都必须让位。** 这是派生幂等的唯一依据：
#: production 为 ``lib/service/<service>/<context>/<object>/<layer>/...``（层内允许
#: 可选子路径，与云侧 ``<service>/internal/<ctx>/<obj>/adapters/inbound/http/``
#: 同构），test 为
#: ``test/<test_layer>/service/<service>/<context>/<object>/...``，
#: 横切面为 ``lib/runtime/...`` 与 ``lib/design_system/...``。
APP_TARGET_SHAPE_SEGMENTS = 5
APP_TEST_TARGET_SHAPE_SEGMENTS = 4

#: 现状端侧目录名 → 目标层。**只用于尚未搬迁的旧命名**；已处于目标形态的路径由
#: ``derive_app_target_shape_identity`` 的第 4 段精确决定，不进入本表。
#: 未搬迁路径取最右（最具体）的命中段。
APP_LAYER_BY_SEGMENT = {
    # 端侧 presentation ≡ 云侧 adapters/inbound
    "presentation": "presentation",
    "pages": "presentation",
    "page": "presentation",
    "screens": "presentation",
    "views": "presentation",
    "widgets": "presentation",
    "sheets": "presentation",
    "sections": "presentation",
    "components": "presentation",
    "dialogs": "presentation",
    "journeys": "presentation",
    # 端侧 application：用例编排与状态协调
    "application": "application",
    "providers": "application",
    "provider": "application",
    "controllers": "application",
    "notifiers": "application",
    "coordinators": "application",
    "usecases": "application",
    "state": "application",
    # 端侧 adapters ≡ 云侧 infrastructure（出向）
    "adapters": "adapters",
    "remote": "remote_adapters",
    "repositories": "adapters",
    "services": "adapters",
    "infrastructure": "adapters",
    "persistence": "adapters",
    "storage": "adapters",
    "clients": "adapters",
    "gateways": "adapters",
    "transport": "adapters",
    # 端侧 domain：不变式、值对象与领域规则
    "domain": "domain",
    "models": "domain",
    "model": "domain",
    "entities": "domain",
    "value_objects": "domain",
    "rules": "domain",
    "policies": "domain",
    "contracts": "domain",
}

#: ``remote`` 段在端侧同时表达「出向适配」与「云契约客户端」，统一归 adapters。
APP_LAYER_ALIASES = {"remote_adapters": "adapters"}

#: flutter gen-l10n 的配置。`arb-dir` 同时决定 arb 输入与 `app_localizations*.dart`
#: 的生成落点，因此 l10n 根不是可自由搬迁的目录，而是由工具链固定的物理位置。
APP_L10N_CONFIG_PATH = APP_ROOT / "l10n.yaml"


def derive_app_l10n_cross_cutting_root() -> str:
    """从 `quwoquan_app/l10n.yaml` 的 `arb-dir` 派生 l10n 横切根段。

    这是 l10n 根的唯一真相源：门禁不得另写死 ``"l10n"`` 字面量，否则改 `arb-dir`
    会让「R1 顶层白名单」与「派生器横切根」再次分叉。
    """
    document = (
        yaml.safe_load((ROOT / APP_L10N_CONFIG_PATH).read_text(encoding="utf-8")) or {}
    )
    arb_dir = str(document.get("arb-dir") or "").strip().strip("/")
    if not arb_dir.startswith("lib/"):
        raise ValueError(
            f"{APP_L10N_CONFIG_PATH.as_posix()}: arb-dir 必须位于 lib/ 之下，"
            f"实测 {arb_dir!r}"
        )
    return arb_dir[len("lib/") :].split("/")[0]


#: 横切面根：不归属任何 business object 的端侧文件的唯一落点，也是 `lib/` 顶层
#: 除 service 容器与入口文件之外允许存在的全部目录。三个根都是**终态**位置：
#: `runtime` / `design_system` 由本文件定义，l10n 根由 `l10n.yaml` 派生。
#: 顶层白名单（`verify_app_architecture.allowed_top_level_directories`）与这里必须
#: 是同一份集合；分叉会让某个根同时是「合法顶层」与「待搬迁横切件」，从而在
#: 覆盖率归属上既不算对象也不算 canonical 横切，整批文件变成无主源码。
APP_CROSS_CUTTING_ROOTS = {
    root: f"lib/{root}"
    for root in sorted(
        {"design_system", "runtime", derive_app_l10n_cross_cutting_root()}
    )
}

#: 横切面根在 ``lib/`` 之下的顶层段，由 APP_CROSS_CUTTING_ROOTS 派生而非另写死。
#: 用于识别「已经搬到横切面目标位置」的路径，避免再套一层根段。
APP_CROSS_CUTTING_SEGMENTS = {
    relative.split("/", 1)[1]: root
    for root, relative in APP_CROSS_CUTTING_ROOTS.items()
}

#: 命中该段即判定为 design_system 横切面；其余无主端侧文件归 runtime。
#: 仅对**尚未搬迁**的路径生效：已在 ``lib/runtime/`` 之下的 ``theme`` / ``tokens``
#: 子目录属于 runtime，不得因段名被改判到 design_system。
APP_DESIGN_SYSTEM_SEGMENTS = frozenset({"design_system", "theme", "tokens"})

#: 组合根段：端侧装配点，云侧 `cmd/` 的对等物，目标位置是 `lib/runtime/di/`。
#: 组合根的职责就是把多个 domain 的实现接线到一起，因此它按定义横跨 domain、
#: 不承载任何单一对象身份。`verify_app_architecture.py` 的横切面反向依赖豁免与
#: 本文件的对象反推共用这一个常量，避免两处各写一份组合根定义。
APP_COMPOSITION_ROOT_SEGMENT = "di"

#: 组合根在 `lib/` 之下的目标前缀，由横切根与组合根段派生而非另写死。
APP_COMPOSITION_ROOT_TARGET_PREFIX = (
    f"{APP_CROSS_CUTTING_ROOTS['runtime'].split('/', 1)[1]}/"
    f"{APP_COMPOSITION_ROOT_SEGMENT}/"
)

#: `lib/` 顶层唯一允许的文件形态：Flutter 入口，云侧 `cmd/main.go` 的端侧对等物。
#: 入口位置由 Flutter 工具链固定（`lib/main*.dart`），它既不属于任何 business
#: object，也**不是待搬迁的横切件**——把它推去 `lib/runtime/main.dart` 会让 App
#: 跑不起来。因此入口文件的横切目标路径就是它自己。
#: `verify_app_architecture.TOP_LEVEL_ENTRY_RE` 直接复用本常量，不另写一份。
APP_ENTRY_FILE_RE = re.compile(r"^main[a-z0-9_]*\.dart$")

#: 横切面目标路径构造时可剥离的现状前缀段（避免 `lib/runtime/core/...` 冗余）。
#: 目标根自身的段（`runtime` / `design_system`）也必须剥离，否则已搬迁路径会被
#: 反复套壳成 `lib/runtime/runtime/di/...`，派生失去幂等。
APP_CROSS_CUTTING_STRIPPED_PREFIXES = ("core",)

#: 对象别名裁剪后缀：端侧现状目录普遍省略 `_view` / `_fact` 语义后缀。
ALIAS_TRIM_SUFFIXES = ("_view", "_fact")

#: 认领方法 → 置信度。已处于目标形态的物理位置与云侧同级，是最强信号。
CLAIM_METHOD_CONFIDENCE = {
    "cloud_path_exact": "exact",
    "app_target_shape": "exact",
    "page_object_contract": "exact",
    "path_object_scoped": "high",
    "path_object_global": "medium",
    "filename_object_scoped": "medium",
    "filename_object_qualified": "medium",
    "context_only": "scope",
    "domain_only": "scope",
    "cross_cutting": "cross_cutting",
    "test_non_object_identity": "cross_cutting",
    "unowned": "none",
}
