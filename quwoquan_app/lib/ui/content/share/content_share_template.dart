import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

class ContentShareAction {
  const ContentShareAction({required this.id, required this.label});

  final String id;
  final String label;
}

class ContentShareTemplate {
  const ContentShareTemplate({
    required this.profileId,
    required this.layout,
    required this.permission,
    required this.deeplink,
    required this.landingPage,
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

  final String profileId;
  final String layout;
  final String permission;
  final String deeplink;
  final String landingPage;
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

  /// 应用内 scheme 链接（`quwoquan://…`），与发现/作品流 [DefaultContentShareActionHandler] 复制逻辑一致。
  ///
  /// 站外 HTTPS 请使用 [AppPublicContentLinks.postWebUrl]。
  static String appSchemePostUrl(String postId, {String visibility = 'public'}) {
    final permission = _normalizeVisibility(visibility);
    return AppLinkTemplates.postAppDeepLink(
      postId,
      visibilityIsCircleVisible: permission == 'circle_visible',
    );
  }

  static ContentShareTemplate build({
    required PostBaseDto post,
    required bool enableIdentityTemplate,
    String visibility = 'public',
    List<String> circleNames = const <String>[],
    List<String> tags = const <String>[],
  }) {
    final permission = _normalizeVisibility(visibility);
    if (!enableIdentityTemplate) {
      return _buildLegacyTemplate(post: post, permission: permission);
    }
    if (permission == 'private') {
      return ContentShareTemplate(
        profileId: post.identity,
        layout: 'blocked',
        permission: permission,
        deeplink: '',
        landingPage: 'blocked',
        title: UITextConstants.shareTo,
        subtitle: UITextConstants.sharePrivateBlocked,
        shareTitle: _shareSeedForPost(post).title,
        shareSummary: _shareSeedForPost(post).summary,
        coverUrl: _shareSeedForPost(post).coverUrl,
        actions: const <ContentShareAction>[],
        isIdentityTemplate: true,
        isBlocked: true,
        notice: UITextConstants.sharePrivateBlocked,
      );
    }

    final profile = _profileForIdentity(post.identity);
    final shareSeed = _shareSeedForPost(post);
    final deeplink = AppLinkTemplates.postAppDeepLink(
      post.id,
      visibilityIsCircleVisible: permission == 'circle_visible',
    );
    final summary = _decorateSummary(
      base: shareSeed.summary,
      includeCircleContext: profile.includeCircleContext,
      includeTimeContext: profile.includeTimeContext,
      circleNames: circleNames,
      createdAt: post.createdAt,
    );
    final tagSummary = profile.includeTags && tags.isNotEmpty
        ? '${summary.isEmpty ? '' : '$summary · '}#${tags.join(' #')}'
        : summary;

    return ContentShareTemplate(
      profileId: profile.id,
      layout: profile.layout,
      permission: permission,
      deeplink: deeplink,
      landingPage: post.identity == 'moment'
          ? 'moment_landing'
          : 'work_landing',
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
      isIdentityTemplate: true,
      isBlocked: false,
      notice: permission == 'circle_visible'
          ? UITextConstants.shareCircleVisibilityNotice
          : null,
    );
  }

  static ContentShareTemplate _buildLegacyTemplate({
    required PostBaseDto post,
    required String permission,
  }) {
    final shareSeed = _shareSeedForPost(post);
    return ContentShareTemplate(
      profileId: 'legacy',
      layout: 'legacy_sheet',
      permission: permission,
      deeplink: permission == 'private'
          ? ''
          : AppLinkTemplates.postAppDeepLink(
              post.id,
              visibilityIsCircleVisible: permission == 'circle_visible',
            ),
      landingPage: 'legacy_content',
      title: UITextConstants.shareTo,
      subtitle: UITextConstants.shareLegacyFallbackNotice,
      shareTitle: shareSeed.title,
      shareSummary: shareSeed.summary,
      coverUrl: shareSeed.coverUrl,
      actions: permission == 'private'
          ? const <ContentShareAction>[]
          : const <ContentShareAction>[
              ContentShareAction(
                id: 'copy_link',
                label: UITextConstants.copyLink,
              ),
            ],
      isIdentityTemplate: false,
      isBlocked: permission == 'private',
      notice: permission == 'private'
          ? UITextConstants.sharePrivateBlocked
          : UITextConstants.shareLegacyFallbackNotice,
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
      case 'circle-visible':
      case 'circle_visible':
      case 'circle':
        return 'circle_visible';
      default:
        return 'public';
    }
  }

  static _ShareSeed _shareSeedForPost(PostBaseDto post) {
    if (post.isArticleLike) {
      return _ShareSeed(
        title: _clip(post.normalizedTitle, fallback: '作品'),
        summary: _clip(post.normalizedBody, maxLength: 48),
        coverUrl: post.primaryVisualUrl,
      );
    }
    if (post.isVideoLike) {
      return _ShareSeed(
        title: _clip(post.normalizedBody, fallback: '${post.displayName} 的视频作品'),
        summary: _clip(post.normalizedBody, maxLength: 48),
        coverUrl: post.primaryVisualUrl,
      );
    }
    if (post.hasImages || post.mediaCoverUrl.isNotEmpty) {
      return _ShareSeed(
        title: _clip(post.normalizedBody, fallback: '${post.displayName} 的图片作品'),
        summary: _clip(post.normalizedBody, maxLength: 48),
        coverUrl: post.primaryVisualUrl,
      );
    }
    if (post.identity == 'moment') {
      return _ShareSeed(
        title: _clip(post.normalizedBody, fallback: '${post.displayName} 的点滴'),
        summary: _clip(post.normalizedBody, maxLength: 48),
        coverUrl: post.primaryVisualUrl,
      );
    }
    return _ShareSeed(
      title: _clip(post.displayName, fallback: '内容分享'),
      summary: '',
      coverUrl: '',
    );
  }

  static String _decorateSummary({
    required String base,
    required bool includeCircleContext,
    required bool includeTimeContext,
    required List<String> circleNames,
    required DateTime createdAt,
  }) {
    final parts = <String>[];
    if (base.isNotEmpty) {
      parts.add(base);
    }
    if (includeCircleContext && circleNames.isNotEmpty) {
      parts.add(circleNames.join(' / '));
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
