#!/usr/bin/env python3
"""登录入口无死循环契约静态门禁。

阻断回退回归：
1. 首页关注频道登录关闭后 pop 回触发点再次弹登录。
2. createEntry / 加号入口被路由守卫提前拦截，未进入具体动作就弹登录。
3. Web/宽屏创作主入口未登录直接显示登录面板。
4. 活动/群聊具体动作绕过 gate，或登录成功后没有 typed continuation 精确续接。
5. 缺少「关闭不回环」与「登录成功进目标态」回归测试。
6. 鉴权双真相源回归：`page_object_contract.yaml` 的 auth_requirement 与
   `requiredRouteGateForLocation` 漂移（缺 parity 测试、守卫丢 RTC/settings
   分支、auth_gate 重新引入裸路径前缀字面量）。
"""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def block_between(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        return text[start_index:]
    return text[start_index:end_index]


def main() -> int:
    errors: list[str] = []

    auth_continuation = read("quwoquan_app/lib/runtime/auth/auth_continuation.dart")
    home_page = read(
        "quwoquan_app/lib/service/content_service/content/post/presentation/home_page.dart"
    )
    auth_gate = read("quwoquan_app/lib/runtime/auth/auth_gate.dart")
    create_action_sheet = read(
        "quwoquan_app/lib/service/content_service/content/post/presentation/create_action_sheet.dart"
    )
    quick_actions = read(
        "quwoquan_app/lib/runtime/shell/actions/global_surface_actions.dart"
    )
    global_surface_action_dependencies = read(
        "quwoquan_app/lib/runtime/di/global_surface_action_dependencies.dart"
    )
    create_entry_route = read(
        "quwoquan_app/lib/runtime/di/navigation/app_router.dart"
    )
    main_shell = read("quwoquan_app/lib/runtime/shell/main_app_shell.dart")
    shell_test = read("quwoquan_app/test/local_contract/runtime/shell/main_app_shell_widget__local_contract_test.dart")
    continuation_test = read(
        "quwoquan_app/test/local_contract/runtime/auth/auth_continuation__local_contract_test.dart"
    )
    create_entry_test = read(
        "quwoquan_app/test/local_contract/service/content_service/content/post/widgets/create_entry_sheet_widget__local_contract_test.dart"
    )
    web_create_test = read(
        "quwoquan_app/test/local_contract/runtime/shell/web_create_groups__local_contract_test.dart"
    )
    route_test = read(
        "quwoquan_app/test/local_contract/runtime/auth/required_route_gate__local_contract_test.dart"
    )

    require(
        "class OpenHomeChannelContinuation extends AuthContinuation" in auth_continuation,
        "缺少 OpenHomeChannelContinuation：首页关注等内部 tab 必须用 continuation 区分关闭态与成功目标态",
        errors,
    )

    following_block = block_between(
        home_page,
        "AuthGateReason.followingFeed",
        "return;",
    )
    require(
        "OpenHomeChannelContinuation" in home_page,
        "HomePage 未登记 OpenHomeChannelContinuation，登录成功无法进入关注目标态",
        errors,
    )
    require(
        "dismissPolicy: LoginDismissPolicy.safeFallback" in following_block,
        "关注频道登录门必须使用 LoginDismissPolicy.safeFallback，禁止关闭后 pop 回触发点",
        errors,
    )
    require(
        "redirect: AppRoutePaths.home" in following_block
        and "dismissFallback: AppRoutePaths.home" in following_block,
        "关注频道登录门必须显式声明 redirect/dismissFallback 为首页安全态",
        errors,
    )
    require(
        ".take<OpenHomeChannelContinuation>()" in home_page,
        "HomePage 必须消费 OpenHomeChannelContinuation，登录成功后进入关注频道",
        errors,
    )

    require(
        "loc == AppRoutePaths.createEntry" not in auth_gate,
        "createEntry 是添加动作面板入口，禁止路由守卫提前拦截为 createPost",
        errors,
    )
    require(
        "loc == AppRoutePaths.createPathTemplate" in auth_gate
        and "return AuthGateReason.createPost" in block_between(
            auth_gate,
            "loc == AppRoutePaths.createPathTemplate",
            "if (loc == AppRoutePaths.chat",
        ),
        "/create 具体创作页必须仍由路由守卫保护",
        errors,
    )

    require(
        "startGathering," in auth_continuation
        and "AuthContinuationSheet.startGathering" in quick_actions,
        "发起活动必须声明强类型 AuthContinuationSheet.startGathering 并由壳层续接",
        errors,
    )
    require(
        "AuthGateReason.startGathering: AuthGateEntry(" in auth_gate
        and "reason: AuthGateReason.startGathering" in auth_gate,
        "发起活动必须进入 AuthGateReason.startGathering 登录门矩阵",
        errors,
    )
    require(
        "openGatedStartGathering" in create_entry_route,
        "createEntry 发起活动必须走 openGatedStartGathering，禁止绕过登录门",
        errors,
    )
    require(
        "openGatedStartGroupChat" in create_entry_route,
        "createEntry 发起群聊必须走 openGatedStartGroupChat，禁止绕过登录门",
        errors,
    )
    gated_action_block = block_between(
        quick_actions,
        "static Future<void> _runGatedSheetAction(",
        "\n}\n\nenum _QuickActionIntentKind",
    )
    require(
        "dismissFallback: AppRoutePaths.home" in gated_action_block
        and "dismissPolicy: LoginDismissPolicy.safeFallback" in gated_action_block,
        "活动/群聊动作登录门关闭时必须回首页安全态，禁止 pop 回入口",
        errors,
    )
    require(
        "Provider<GatheringCreateNavigationBinding?>"
        in global_surface_action_dependencies
        and "AppRoutePaths.gatheringCreate"
        in global_surface_action_dependencies
        and "extra: request" in global_surface_action_dependencies
        and "globalSurfaceActionBindingsProvider" in quick_actions,
        "活动 canonical route codegen 后必须由 typed binding 进入 generated gatheringCreate 并保留请求",
        errors,
    )
    require(
        "loc == AppRoutePaths.gatheringCreate" in auth_gate
        and "return AuthGateReason.startGathering" in block_between(
            auth_gate,
            "loc == AppRoutePaths.gatheringCreate",
            "if (loc == AppRoutePaths.blockedUsers",
        ),
        "gatheringCreate 必须由直达路由守卫映射到 startGathering 强登录门",
        errors,
    )

    primary_block = block_between(
        create_action_sheet,
        "final primaryActions = <_SheetActionSpec>[",
        "final contentActions = <_SheetActionSpec>[",
    )
    content_block = block_between(
        create_action_sheet,
        "final contentActions = <_SheetActionSpec>[",
        "final actions = _showsContentActions",
    )
    require(
        all(
            needle in primary_block
            for needle in (
                "createActionPublishContent",
                "createActionStartGathering",
                "createActionStartGroupChat",
            )
        ),
        "创作入口首层必须固定为发内容/发起活动/发起群聊",
        errors,
    )
    require(
        all(
            needle in content_block
            for needle in (
                "createActionGallery",
                "createActionCapture",
                "createActionWrite",
            )
        ),
        "发内容二级必须固定为照片/视频/文字",
        errors,
    )
    require(
        all(
            needle not in create_action_sheet
            for needle in ("onAddContact", "onCreateCircle", "onInterestMatch")
        ),
        "加好友/建圈/兴趣配对必须移出 C 位/CreateEntry 首层",
        errors,
    )

    web_tap_block = block_between(
        main_shell,
        "void _handleWebPrimaryTap(MainTabDestination nextTab)",
        "void _selectWebCreateTab()",
    )
    web_create_block = block_between(
        web_tap_block,
        "if (nextTab == MainTabDestination.create)",
        "if (nextTab == MainTabDestination.chat",
    )
    require(
        "_selectWebCreateTab();" in web_create_block,
        "Web/宽屏 create 主入口必须先进入创建工作台",
        errors,
    )
    require(
        "_showWebLoginSurface" not in web_create_block,
        "Web/宽屏 create 主入口禁止未登录直接显示登录覆盖层",
        errors,
    )

    required_tests = {
        "关注关闭不回环": "游客点击首页关注 tab 关闭登录页后回首页且不回环",
        "关注登录成功目标态": "游客点击首页关注 tab 登录成功后进入关注频道目标态",
        "createEntry 不提前拦截": "游客直达 createEntry 显示动作面板入口，不被创作路由门提前拦截",
        "/create 仍拦截": "游客直达 /create 具体创作页仍被路由门拦截，关闭回首页",
        "Gathering Create 关闭不回环": "游客直达发起活动，关闭登录回安全首页且不回环",
        "Web create 不直接登录": "Web 宽屏未登录点创作主入口先进入创建工作台，不直接登录",
    }
    for name, needle in required_tests.items():
        require(needle in shell_test, f"缺少登录入口回环回归测试：{name}", errors)

    require(
        "发起活动续接精确调用组合根注入的 typed navigation binding"
        in continuation_test,
        "缺少发起活动登录成功后精确调用 typed navigation binding 的 continuation 测试",
        errors,
    )
    require(
        all(
            needle in create_entry_test
            for needle in (
                "TestKeys.createActionPublishContent",
                "TestKeys.createActionStartGathering",
                "TestKeys.createActionStartGroupChat",
                "TestKeys.createActionGallery",
                "TestKeys.createActionCapture",
                "TestKeys.createActionWrite",
            )
        ),
        "缺少 mobile/createEntry 首层 3 项 + 发内容二级 3 项测试",
        errors,
    )
    require(
        all(
            needle in web_create_test
            for needle in (
                "TestKeys.webCreateActionPublishContent",
                "TestKeys.webCreateActionStartGathering",
                "TestKeys.webCreateActionStartGroupChat",
                "web-create-card-album",
                "web-create-card-camera",
                "web-create-card-write",
            )
        ),
        "缺少 Web 创作工作台首层 3 项 + 发内容二级 3 项测试",
        errors,
    )
    require(
        "游客从网页发起活动先登录，关闭后回安全首页且不回环" in web_create_test,
        "缺少发起活动具体动作的游客登录关闭安全态与不回环测试",
        errors,
    )

    require(
        "requiredRouteGateForLocation(AppRoutePaths.createEntry), isNull" in route_test,
        "required_route_gate_test 必须断言 createEntry 不被路由守卫拦截",
        errors,
    )
    require(
        re.search(
            r"requiredRouteGateForLocation\(AppRoutePaths\.createPathTemplate\),\s*AuthGateReason\.createPost",
            route_test,
            re.S,
        )
        is not None,
        "required_route_gate_test 必须断言 /create 具体创作页仍需登录",
        errors,
    )
    require(
        re.search(
            r"requiredRouteGateForLocation\(AppRoutePaths\.gatheringCreate\),\s*AuthGateReason\.startGathering",
            route_test,
            re.S,
        )
        is not None,
        "required_route_gate_test 必须断言 gatheringCreate 使用 startGathering 强登录门",
        errors,
    )

    # ---- 鉴权声明 ↔ 路由守卫零漂移（契约 required 深链不得绕过登录门）----
    parity_test_path = (
        ROOT
        / "quwoquan_app/test/local_contract/runtime/auth/"
        / "route_auth_contract_parity__local_contract_test.dart"
    )
    require(
        parity_test_path.is_file(),
        "缺少 route_auth_contract_parity__local_contract_test.dart："
        "契约 auth_requirement 与 requiredRouteGateForLocation 的零漂移测试",
        errors,
    )
    if parity_test_path.is_file():
        parity_test = parity_test_path.read_text(encoding="utf-8")
        require(
            "page_object_contract.yaml" in parity_test
            and "app_routes.yaml" in parity_test,
            "parity 测试必须直接消费 page_object_contract.yaml 与 app_routes.yaml，"
            "禁止手抄第二份 required 路由清单",
            errors,
        )
        require(
            "required 的 routed 页深链必须被路由守卫拦截" in parity_test
            and "禁止被守卫整页拦截" in parity_test,
            "parity 测试必须双向断言：required 拦截 + optional/public 不拦截",
            errors,
        )
    require(
        "AuthGateReason.startCall;" in auth_gate
        and "rtcIncomingPathTemplate" in auth_gate
        and "rtcPickParticipants" in auth_gate,
        "RTC 通话页族（契约 required）必须由 requiredRouteGateForLocation 映射到 startCall",
        errors,
    )
    require(
        "_requiredSettingsSubPages" in auth_gate
        and "settingsAccountSecurity" in auth_gate
        and "settingsPrivacy" in auth_gate,
        "账号态设置子页（契约 required）必须由 requiredRouteGateForLocation 拦截",
        errors,
    )
    require(
        "'/chat/'" not in auth_gate and "'/profile/'" not in auth_gate,
        "auth_gate 禁止裸路径前缀字面量，必须从 AppRoutePaths 常量拼接",
        errors,
    )

    if errors:
        print("FAIL: 登录入口无死循环契约校验未通过：")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("OK: 登录入口无死循环契约一致（关闭回安全态，登录进目标态）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
