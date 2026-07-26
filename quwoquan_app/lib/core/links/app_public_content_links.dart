import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';

/// 面向用户/站外分享的公网链接。
///
/// - **路径形态** 由 metadata `link_templates.yaml` codegen（[AppLinkTemplates]）提供；本类只读 **运行时 origin**。
/// - `quwoquan.com` 申请完成前默认复用当前环境 IP gateway；正式域名通过
///   `--dart-define=PUBLIC_WEB_BASE_URL=https://quwoquan.com` 单点覆盖。
class AppPublicContentLinks {
  AppPublicContentLinks._();

  static const String _publicWebBaseUrlOverride = String.fromEnvironment(
    AppLinkTemplates.publicWebDartDefineKey,
    defaultValue: '',
  );

  /// 公网站点根 URL（无尾斜杠；与 [publicWebUrlForPath] / [postWebUrl] 组合规则一致）。
  ///
  /// 站外分享/PC Web 链接面向公网浏览器，必须是 HTTPS：override 通常已是
  /// `https://quwoquan.com`；过渡期回退当前环境 gateway 时，把开发态的
  /// `http://` origin 升级为 `https://`，避免对外暴露明文 http 公链。
  static String get publicWebBaseUrl {
    final override = _publicWebBaseUrlOverride.trim();
    if (override.isNotEmpty) {
      return override;
    }
    return _forceHttpsOrigin(CloudRuntimeConfig.gatewayBaseUrl);
  }

  static String _forceHttpsOrigin(String base) {
    final value = base.trim();
    if (value.toLowerCase().startsWith('http://')) {
      return 'https://${value.substring('http://'.length)}';
    }
    return value;
  }

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
