// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:yaml/yaml.dart';

/// 「鉴权声明 ↔ 路由守卫」零漂移合约。
///
/// `page_object_contract.yaml` 的 `auth_requirement` 是页面鉴权的声明真相源，
/// `requiredRouteGateForLocation` 是运行时深链守卫的执行真相源。两者必须双向
/// 一致：
/// 1. 契约 `required` 的 routed 页深链直达必须被守卫拦截（否则 settings/RTC
///    等账号态页可被游客深链绕过）；
/// 2. 契约 `optional` / `public` 的 routed 页禁止被守卫整页拦截（否则登录页
///    关闭后原路返回会再次命中守卫，形成「关闭→又弹登录」死循环）。
void main() {
  late final Map<String, String> routePathById;
  late final List<_RoutedPage> routedPages;

  setUpAll(() {
    final repoRoot = _findRepoRoot();
    final sharedMetadata = Directory(
      '${repoRoot.path}/quwoquan_service/contracts/metadata/_shared',
    );

    final routesDoc = loadYaml(
      File('${sharedMetadata.path}/app_routes.yaml').readAsStringSync(),
    ) as YamlMap;
    routePathById = <String, String>{
      for (final route in routesDoc['routes'] as YamlList)
        (route as YamlMap)['id'] as String: route['path'] as String,
    };

    final contractDoc = loadYaml(
      File(
        '${sharedMetadata.path}/page_object_contract.yaml',
      ).readAsStringSync(),
    ) as YamlMap;
    routedPages = <_RoutedPage>[
      for (final page in contractDoc['pages'] as YamlList)
        if ((page as YamlMap)['page_kind'] == 'routed')
          _RoutedPage(
            pageId: page['page_id'] as String,
            authRequirement: page['auth_requirement'] as String,
            routeId: page['route_id'] as String,
          ),
    ];
  });

  test('契约中每个 routed 页的 route_id 都能解析出 path', () {
    for (final page in routedPages) {
      expect(
        routePathById,
        contains(page.routeId),
        reason: '页面 ${page.pageId} 的 route_id ${page.routeId} '
            '在 app_routes.yaml 中不存在',
      );
    }
    expect(routedPages, isNotEmpty);
  });

  test('auth_requirement: required 的 routed 页深链必须被路由守卫拦截', () {
    final unguarded = <String>[];
    for (final page in routedPages) {
      if (page.authRequirement != 'required') {
        continue;
      }
      final location = _sampleLocation(routePathById[page.routeId]!);
      if (requiredRouteGateForLocation(location) == null) {
        unguarded.add('${page.pageId} -> $location');
      }
    }
    expect(
      unguarded,
      isEmpty,
      reason: '以下契约 required 页面深链直达未被 requiredRouteGateForLocation '
          '拦截，游客可绕过登录门：\n${unguarded.join('\n')}',
    );
  });

  test('auth_requirement: optional/public 的 routed 页禁止被守卫整页拦截', () {
    final overGuarded = <String>[];
    for (final page in routedPages) {
      if (page.authRequirement == 'required') {
        continue;
      }
      final location = _sampleLocation(routePathById[page.routeId]!);
      final gate = requiredRouteGateForLocation(location);
      if (gate != null) {
        overGuarded.add('${page.pageId} -> $location (${gate.name})');
      }
    }
    expect(
      overGuarded,
      isEmpty,
      reason: '以下游客可浏览页面被路由守卫整页拦截，登录页关闭后将原路返回并'
          '再次命中守卫形成死循环：\n${overGuarded.join('\n')}',
    );
  });

  test('守卫拦截的登录跳转对 required 页一律使用安全关闭兜底', () {
    // 与 app_router.redirect 的写法同构：守卫命中时 dismissPolicy 必须是
    // safeFallback，且 safeLoginDismissFallback 不会回到受限路由本身。
    for (final page in routedPages) {
      if (page.authRequirement != 'required') {
        continue;
      }
      final location = _sampleLocation(routePathById[page.routeId]!);
      final fallback = safeLoginDismissFallback(redirect: location);
      expect(
        requiredRouteGateForLocation(fallback),
        isNull,
        reason: '${page.pageId} 的登录关闭兜底 $fallback 仍是受限路由，会造成回环',
      );
    }
  });
}

class _RoutedPage {
  const _RoutedPage({
    required this.pageId,
    required this.authRequirement,
    required this.routeId,
  });

  final String pageId;
  final String authRequirement;
  final String routeId;
}

/// 把 `/chat/{id}/board` 一类路径模板填充为可匹配的样例 location。
/// 参数值避开 `create` 等真实静态段，防止与兄弟路由的精确匹配撞车。
String _sampleLocation(String pathTemplate) {
  return pathTemplate.replaceAllMapped(
    RegExp(r'\{[^}]+\}'),
    (_) => 'sample-id',
  );
}

Directory _findRepoRoot() {
  var dir = Directory.current;
  while (true) {
    if (File(
      '${dir.path}/quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml',
    ).existsSync()) {
      return dir;
    }
    final parent = dir.parent;
    if (parent.path == dir.path) {
      throw StateError('未能从 ${Directory.current.path} 向上定位仓库根');
    }
    dir = parent;
  }
}
