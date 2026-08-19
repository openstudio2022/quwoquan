import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';

/// 面向用户/站外分享的公网链接。
///
/// - **路径形态** 由 metadata `link_templates.yaml` codegen（[AppLinkTemplates]）提供；本类只读 **运行时 origin**。
/// - 四环境官方 Web origin 由 [CloudRuntimeConfig.publicWebBaseUrl] 单点注入。
final class PublicContentLinkBuilder {
  PublicContentLinkBuilder(Uri publicWebOrigin)
    : publicWebOrigin = _validateAndNormalize(publicWebOrigin);

  factory PublicContentLinkBuilder.fromRuntimeConfig() {
    return PublicContentLinkBuilder(
      Uri.parse(CloudRuntimeConfig.publicWebBaseUrl),
    );
  }

  final Uri publicWebOrigin;

  static Uri _validateAndNormalize(Uri value) {
    if (value.scheme != 'https' ||
        value.host.isEmpty ||
        value.userInfo.isNotEmpty ||
        value.hasQuery ||
        value.hasFragment) {
      throw ArgumentError.value(
        value,
        'publicWebOrigin',
        'Public Web origin must be an HTTPS base URL without credentials, query, or fragment',
      );
    }
    final normalizedPath = value.path.replaceAll(RegExp(r'/+$'), '');
    return value.replace(path: normalizedPath);
  }

  String publicWebUrlForPath(String relativePath) {
    final path = relativePath.trim();
    if (path.isEmpty) return publicWebOrigin.toString();
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return '${publicWebOrigin.toString()}$normalizedPath';
  }

  String postWebUrl(String postId) =>
      publicWebUrlForPath(AppLinkTemplates.postWebPath(postId));

  String entityHomepageWebUrl(String homepageId) =>
      publicWebUrlForPath(AppLinkTemplates.entityHomepageWebPath(homepageId));

  String circleWebUrl(String circleId) =>
      publicWebUrlForPath(AppLinkTemplates.circleWebPath(circleId));

  String siteOriginForHttpHeaders() => publicWebOrigin.toString();
}

/// 生产便利 facade；需要确定性输入的调用方直接依赖 [PublicContentLinkBuilder]。
class AppPublicContentLinks {
  AppPublicContentLinks._();

  static PublicContentLinkBuilder get _builder =>
      PublicContentLinkBuilder.fromRuntimeConfig();

  /// 公网站点根 URL（无尾斜杠；与 [publicWebUrlForPath] / [postWebUrl] 组合规则一致）。
  static String get publicWebBaseUrl => _builder.publicWebOrigin.toString();

  /// 将 metadata 生成的 **相对 origin** 路径（无首 `/`）拼成完整 URL。
  static String publicWebUrlForPath(String relativePath) {
    return _builder.publicWebUrlForPath(relativePath);
  }

  /// 帖子站外分享/复制用 HTTPS 链接（浏览器可打开）。
  static String postWebUrl(String postId) => _builder.postWebUrl(postId);

  /// 实体主页站外分享/PC Web 用 HTTPS 链接。
  static String entityHomepageWebUrl(String homepageId) =>
      _builder.entityHomepageWebUrl(homepageId);

  /// 圈子主页站外分享/复制用 HTTPS 链接（浏览器可打开）。
  static String circleWebUrl(String circleId) =>
      _builder.circleWebUrl(circleId);

  /// HTTP `Referer` / 品牌来源等场景使用的站点根（无路径）。
  static String siteOriginForHttpHeaders() =>
      _builder.siteOriginForHttpHeaders();
}
