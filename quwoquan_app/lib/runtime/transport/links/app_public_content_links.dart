import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';

/// 面向用户/站外分享的公网链接。
///
/// - **路径形态** 由 metadata `link_templates.yaml` codegen（[AppLinkTemplates]）提供；本类只读 **运行时 origin**。
/// - 四环境官方 Web origin 由 [CloudRuntimeConfig.publicWebBaseUrl] 单点注入。
class AppPublicContentLinks {
  AppPublicContentLinks._();

  /// 公网站点根 URL（无尾斜杠；与 [publicWebUrlForPath] / [postWebUrl] 组合规则一致）。
  static String get publicWebBaseUrl => CloudRuntimeConfig.publicWebBaseUrl;

  static String _normalizedBase() {
    return publicWebBaseUrl.trim().replaceAll(RegExp(r'/+$'), '');
  }

  /// 将 metadata 生成的 **相对 origin** 路径（无首 `/`）拼成完整 URL。
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

  /// 实体主页站外分享/PC Web 用 HTTPS 链接。
  static String entityHomepageWebUrl(String homepageId) =>
      publicWebUrlForPath(AppLinkTemplates.entityHomepageWebPath(homepageId));

  /// 圈子主页站外分享/复制用 HTTPS 链接（浏览器可打开）。
  static String circleWebUrl(String circleId) =>
      publicWebUrlForPath(AppLinkTemplates.circleWebPath(circleId));

  /// HTTP `Referer` / 品牌来源等场景使用的站点根（无路径）。
  static String siteOriginForHttpHeaders() => _normalizedBase();
}
