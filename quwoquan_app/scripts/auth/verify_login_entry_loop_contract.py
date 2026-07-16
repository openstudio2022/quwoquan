#!/usr/bin/env python3
"""登录入口无死循环契约静态门禁。

阻断回退回归：
1. 首页关注频道登录关闭后 pop 回触发点再次弹登录。
2. createEntry / 加号入口被路由守卫提前拦截，未进入具体动作就弹登录。
3. Web/宽屏创作主入口未登录直接显示登录面板。
4. 缺少「关闭不回环」与「登录成功进目标态」回归测试。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


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

    auth_continuation = read("quwoquan_app/lib/core/auth/auth_continuation.dart")
    home_page = read("quwoquan_app/lib/ui/discovery/pages/home_page.dart")
    auth_gate = read("quwoquan_app/lib/core/auth/auth_gate.dart")
    main_shell = read("quwoquan_app/lib/app/shell/main_app_shell.dart")
    shell_test = read("quwoquan_app/test/local_contract/app/shell/main_app_shell_widget__local_contract_test.dart")
    route_test = read("quwoquan_app/test/local_contract/core/auth/required_route_gate__local_contract_test.dart")

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
        "Web create 不直接登录": "Web 宽屏未登录点创作主入口先进入创建工作台，不直接登录",
    }
    for name, needle in required_tests.items():
        require(needle in shell_test, f"缺少登录入口回环回归测试：{name}", errors)

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

    if errors:
        print("FAIL: 登录入口无死循环契约校验未通过：")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("OK: 登录入口无死循环契约一致（关闭回安全态，登录进目标态）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
