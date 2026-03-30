import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';

/// 面向用户/站外分享的 **公网 HTTPS 链接**（与 API [CloudRuntimeConfig.gatewayBaseUrl] 分离）。
///
/// - **路径形态** 由 metadata `link_templates.yaml` codegen（[AppLinkTemplates]）提供；本类只读 **运行时 origin**。
/// - 过渡期通过 `--dart-define=PUBLIC_WEB_BASE_URL=https://…` 覆盖（与 [AppLinkTemplates.publicWebDartDefineKey] 一致）。
class AppPublicContentLinks {
  AppPublicContentLinks._();

  /// 公网站点根 URL（无尾斜杠；与 [publicWebUrlForPath] / [postWebUrl] 组合规则一致）。
  static const String publicWebBaseUrl = String.fromEnvironment(
    AppLinkTemplates.publicWebDartDefineKey,
    defaultValue: 'https://quwoquan.app',
  );

  static String _normalizedBase() {
    return publicWebBaseUrl.trim().replaceAll(RegExp(r'/+$'), '');
  }

  /// 将 metadata 生成的 **相对 origin** 路径（无首 `/`）拼成完整 HTTPS URL。
  static String publicWebUrlForPath(String relativePath) {
    final path = relativePath.trim();
    if (path.isEmpty) return _normalizedBase();
    final base = _normalizedBase();
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return '$base$normalizedPath';
  }

  /// 帖子站外分享/复制用 HTTPS 链接（浏览器可打开）。
  static String postWebUrl(String postId) =>
      publicWebUrlForPath(AppLinkTemplates.postWebPath(postId));

  /// HTTP `Referer` / 品牌来源等场景使用的站点根（无路径）。
  static String siteOriginForHttpHeaders() => _normalizedBase();
}
