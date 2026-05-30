import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';

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
    ContentSurfaceView? surfaceView,
  }) {
    // 统一展示 model 双读（D1b）：surfaceView 非空（flag 开）时由统一 model 取种子，
    // 否则走旧投影路径。两路径同源（同 DTO → 同字段口径），可单独回退。
    _ShareSeed seedFor() => surfaceView == null
        ? _shareSeedForPost(post)
        : _shareSeedForSurfaceView(surfaceView);

    final permission = _normalizeVisibility(visibility);
    if (permission == 'private') {
      final blockedSeed = seedFor();
      return ContentShareTemplate(
        profileId: post.identity,
        layout: 'blocked',
        permission: permission,
        deeplink: '',
        landingPage: 'blocked',
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

    final profile = _profileForIdentity(post.identity);
    final shareSeed = seedFor();
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
      isIdentityTemplate: enableIdentityTemplate,
      isBlocked: false,
      notice: permission == 'circle_visible'
          ? UITextConstants.shareCircleVisibilityNotice
          : null,
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
    final read = PostReadPresentation.fromPostBase(post);
    final cover =
        read.coverUrl.isNotEmpty ? read.coverUrl : post.primaryVisualUrl;
    if (post.isArticleLike) {
      return _ShareSeed(
        title: _clip(read.title, fallback: '作品'),
        summary: _clip(read.body, maxLength: 48),
        coverUrl: cover,
      );
    }
    if (post.isVideoLike) {
      return _ShareSeed(
        title: _clip(read.body, fallback: '${read.displayName} 的视频作品'),
        summary: _clip(read.body, maxLength: 48),
        coverUrl: cover,
      );
    }
    if (post.hasImages || post.mediaCoverUrl.isNotEmpty) {
      return _ShareSeed(
        title: _clip(read.body, fallback: '${read.displayName} 的图片作品'),
        summary: _clip(read.body, maxLength: 48),
        coverUrl: cover,
      );
    }
    if (post.identity == 'moment') {
      return _ShareSeed(
        title: _clip(read.body, fallback: '${read.displayName} 的点滴'),
        summary: _clip(read.body, maxLength: 48),
        coverUrl: cover,
      );
    }
    return _ShareSeed(
      title: _clip(read.displayName, fallback: '内容分享'),
      summary: '',
      coverUrl: cover,
    );
  }

  /// 统一展示 model 路径的分享种子（与 [_shareSeedForPost] 同源口径）。
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
          title: _clip(title, fallback: '作品'),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.video:
        return _ShareSeed(
          title: _clip(body, fallback: '$displayName 的视频作品'),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.image:
        return _ShareSeed(
          title: _clip(body, fallback: '$displayName 的图片作品'),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentSurfaceKind.micro:
        return _ShareSeed(
          title: _clip(body, fallback: '$displayName 的点滴'),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
    }
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
