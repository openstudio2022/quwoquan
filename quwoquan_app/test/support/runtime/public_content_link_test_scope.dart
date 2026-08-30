/// local_contract 测试期的公网站点 origin provisioning。
///
/// ## 为什么需要它
///
/// 生产的站外 origin 只来自 runtime package（`CloudRuntimeConfig.publicWebBaseUrl`），
/// 由 `app_bootstrap` 在启动时水合；`PublicContentLinkBuilder` 对空 origin 是
/// fail-closed 的（缺失键不得拼出半份配置）。裸 `flutter test` 不水合 runtime
/// package，于是「未水合状态下渲染公网链接」在测试里可达，而在生产不可达。
///
/// 正确出路是让测试显式交出自己的 origin，而**不是**在测试里水合全局 runtime
/// package：`CloudRuntimeEnvironment.fromCompileTime()` 读的是同一份配置，一旦水合，
/// `cloudRuntimeEnvironmentProvider` 就变得可构造，Widget 测试会真的去摸 Gateway 并
/// 留下 pending timer——用一批红换另一批红，还掩盖真实的 DI 缺口。
/// 见 quwoquan_app/AGENTS.md「local_contract 测试的 App↔Cloud 边界」。
///
/// ## 两种用法（按被测对象取其一）
///
/// 1. Provider / Widget 测试 → 把 [publicContentLinkOverrides] 展开进 `overrides`。
/// 2. 直接调用 builder / renderer 的对象级测试 → 把 [testPublicContentLinks] 经
///    既有的显式注入参数传进去（例如 `ContentShareTemplateBuilder.build` 的
///    `publicLinks`），并用它拼出期望的绝对 URL 做断言。
///
/// 域名固定用不可解析的 `.test` 保留后缀，与 `testCloudRuntimeEnvironment()` 同源
/// 纪律：万一有测试真的发起请求，也只会立刻失败，不会打到任何真实环境。
library;

import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/di/runtime_package_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';

/// 测试期公网站点 origin（无尾斜杠，与生产 origin 形态一致）。
const String testPublicWebOrigin = 'https://public.example.test';

/// 测试期确定性公网链接 builder。
///
/// 不可变且无状态，故整个套件共享同一实例即可；断言应直接用它拼期望 URL
/// （`testPublicContentLinks.postWebUrl('post_1')`），避免各套件手写 origin 字面量
/// 而出现第二份测试期 base URL。
final PublicContentLinkBuilder testPublicContentLinks = PublicContentLinkBuilder(
  Uri.parse(testPublicWebOrigin),
);

/// Provider / Widget 测试的公网 origin override。
List<Override> publicContentLinkOverrides() => <Override>[
  publicContentLinkBuilderProvider.overrideWithValue(testPublicContentLinks),
];
