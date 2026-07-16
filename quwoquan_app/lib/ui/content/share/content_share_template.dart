import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/links/share_attribution.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';

class ContentShareAction {
  const ContentShareAction({required this.id, required this.label});

  final String id;
  final String label;
}

class ContentShareTemplate {
  const ContentShareTemplate({
    required this.postId,
    required this.profileId,
    required this.layout,
    required this.permission,
    required this.deeplink,
    required this.landingUrl,
    required this.landingPage,
    required this.shareId,
    required this.title,
    required this.subtitle,
    required this.shareTitle,
    required this.shareSummary,
    required this.coverUrl,
    required this.actions,
    required this.isIdentityTemplate,
    required this.isBlocked,
    this.notice,
  });

  final String postId;
  final String profileId;
  final String layout;
  final String permission;
  final String deeplink;
  final String landingUrl;
  final String landingPage;

  /// 单次分享事件归因 id（注入 [landingUrl]，供分享埋点/回流归因同源）。
  final String shareId;
  final String title;
  final String subtitle;
  final String shareTitle;
  final String shareSummary;
  final String coverUrl;
  final List<ContentShareAction> actions;
  final bool isIdentityTemplate;
  final bool isBlocked;
  final String? notice;
}

class ContentShareTemplateBuilder {
  const ContentShareTemplateBuilder._();

  /// 应用内 scheme 链接（`quwoquan://…`），仅作为打开 App 的目标。
  /// 站外复制/系统分享默认必须使用 [publicPostUrl]。
  static String appSchemePostUrl(String postId) =>
      AppLinkTemplates.postAppDeepLink(postId);

  /// 站外公开 HTTPS 链接，作为复制链接/系统分享的默认 URL。
  static String publicPostUrl(String postId) =>
      AppPublicContentLinks.postWebUrl(postId);

  static ContentShareTemplate build({
    required ContentSurfaceView surfaceView,
    required bool enableIdentityTemplate,
    String visibility = 'public',
  }) {
    final permission = _normalizeVisibility(visibility);
    if (permission == 'private') {
      final blockedSeed = _shareSeedForSurfaceView(surfaceView);
      return ContentShareTemplate(
        postId: surfaceView.postId,
        profileId: surfaceView.contentIdentity,
        layout: 'blocked',
        permission: permission,
        deeplink: '',
        landingUrl: '',
        landingPage: 'blocked',
        shareId: '',
        title: UITextConstants.shareTo,
        subtitle: UITextConstants.sharePrivateBlocked,
        shareTitle: blockedSeed.title,
        shareSummary: blockedSeed.summary,
        coverUrl: blockedSeed.coverUrl,
        actions: const <ContentShareAction>[],
        isIdentityTemplate: enableIdentityTemplate,
        isBlocked: true,
        notice: UITextConstants.sharePrivateBlocked,
      );
    }

    final profile = _profileForIdentity(surfaceView.contentIdentity);
    final shareSeed = _shareSeedForSurfaceView(surfaceView);
    final deeplink = AppLinkTemplates.postAppDeepLink(surfaceView.postId);
    // 注入单次分享归因（share_id + UTM），使站外回流可按 share_id/渠道归因。
    final attribution = ShareAttribution.forShareEvent(
      utmSource: ShareAttribution.sourceApp,
      utmMedium: ShareAttribution.mediumSocial,
    );
    final landingUrl = attribution.applyTo(publicPostUrl(surfaceView.postId));
    final summary = _decorateSummary(
      base: shareSeed.summary,
      includeTimeContext: profile.includeTimeContext,
      createdAt: surfaceView.createdAt,
    );
    final tags = surfaceView.tags;
    final tagSummary = profile.includeTags && tags.isNotEmpty
        ? '${summary.isEmpty ? '' : '$summary · '}#${tags.join(' #')}'
        : summary;

    return ContentShareTemplate(
      postId: surfaceView.postId,
      profileId: profile.id,
      layout: profile.layout,
      permission: permission,
      deeplink: deeplink,
      landingUrl: landingUrl,
      landingPage: surfaceView.contentIdentity == 'moment'
          ? 'moment_landing'
          : 'work_landing',
      shareId: attribution.shareId,
      title: UITextConstants.contentLabelForKey(profile.titleKey),
      subtitle: UITextConstants.contentLabelForKey(profile.subtitleKey),
      shareTitle: shareSeed.title,
      shareSummary: tagSummary,
      coverUrl: shareSeed.coverUrl,
      actions: const <ContentShareAction>[
        ContentShareAction(id: 'copy_link', label: UITextConstants.copyLink),
        ContentShareAction(
          id: 'save_poster',
          label: UITextConstants.shareActionSavePoster,
        ),
        ContentShareAction(
          id: 'system_share',
          label: UITextConstants.shareActionSystemShare,
        ),
      ],
      isIdentityTemplate: enableIdentityTemplate,
      isBlocked: false,
      notice: null,
    );
  }

  static ShareTemplateProfileConfig _profileForIdentity(String identity) {
    return ContentUIConfig.shareTemplateProfiles.firstWhere(
      (profile) => profile.id == identity,
      orElse: () => ContentUIConfig.shareTemplateProfiles.last,
    );
  }

  static String _normalizeVisibility(String visibility) {
    final normalized = visibility.trim().toLowerCase();
    switch (normalized) {
      case 'private':
        return 'private';
      case 'public':
        return 'public';
      default:
        throw ArgumentError.value(
          visibility,
          'visibility',
          'Post visibility must be public or private',
        );
    }
  }

  /// 统一展示 model 路径的分享种子（唯一种子来源）。
  static _ShareSeed _shareSeedForSurfaceView(ContentSurfaceView view) {
    final title = view.title ?? '';
    final body = view.body ?? '';
    final displayName = view.author.displayName;
    final cover = view.cover?.url.isNotEmpty == true
        ? view.cover!.url
        : (view.video?.thumbnailUrl.isNotEmpty == true
              ? view.video!.thumbnailUrl
              : (view.images.isNotEmpty ? view.images.first.url : ''));
    switch (view.kind) {
      case ContentSurfaceKind.article:
        return _ShareSeed(
          title: _clip(
            title,
            fallback: UITextConstants.shareSeedWorkFallbackTitle,
          ),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.video:
        return _ShareSeed(
          title: _clip(
            body,
            fallback: UITextConstants.shareSeedVideoWorkTitle(displayName),
          ),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.image:
        return _ShareSeed(
          title: _clip(
            body,
            fallback: UITextConstants.shareSeedImageWorkTitle(displayName),
          ),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.micro:
        return _ShareSeed(
          title: _clip(
            body,
            fallback: UITextConstants.shareSeedMomentTitle(displayName),
          ),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
    }
  }

  static String _decorateSummary({
    required String base,
    required bool includeTimeContext,
    required DateTime createdAt,
  }) {
    final parts = <String>[];
    if (base.isNotEmpty) {
      parts.add(base);
    }
    if (includeTimeContext && createdAt.millisecondsSinceEpoch > 0) {
      final month = createdAt.month.toString().padLeft(2, '0');
      final day = createdAt.day.toString().padLeft(2, '0');
      parts.add('${createdAt.year}-$month-$day');
    }
    return parts.join(' · ');
  }

  static String _clip(String text, {int maxLength = 32, String fallback = ''}) {
    final normalized = text.trim();
    if (normalized.isEmpty) return fallback;
    if (normalized.length <= maxLength) return normalized;
    return '${normalized.substring(0, maxLength)}...';
  }
}

class _ShareSeed {
  const _ShareSeed({
    required this.title,
    required this.summary,
    required this.coverUrl,
  });

  final String title;
  final String summary;
  final String coverUrl;
}
