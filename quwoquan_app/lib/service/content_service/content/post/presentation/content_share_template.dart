import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentType;
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';
import 'package:quwoquan_app/runtime/transport/links/share_attribution.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';

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
    String visibility = 'public',
    PublicContentLinkBuilder? publicLinks,
  }) {
    final permission = _normalizeVisibility(visibility);
    if (permission == 'private') {
      final blockedSeed = _shareSeedForSurfaceView(surfaceView);
      return ContentShareTemplate(
        postId: surfaceView.postId,
        profileId: surfaceView.contentType.wireName,
        layout: 'blocked',
        permission: permission,
        deeplink: '',
        landingUrl: '',
        landingPage: 'blocked',
        shareId: '',
        title: ChatText.shareTo,
        subtitle: ChatText.sharePrivateBlocked,
        shareTitle: blockedSeed.title,
        shareSummary: blockedSeed.summary,
        coverUrl: blockedSeed.coverUrl,
        actions: const <ContentShareAction>[],
        isBlocked: true,
        notice: ChatText.sharePrivateBlocked,
      );
    }

    final profile = _profileForContentType(surfaceView.contentType);
    final shareSeed = _shareSeedForSurfaceView(surfaceView);
    final deeplink = AppLinkTemplates.postAppDeepLink(surfaceView.postId);
    // 注入单次分享归因（share_id + UTM），使站外回流可按 share_id/渠道归因。
    final attribution = ShareAttribution.forShareEvent(
      utmSource: ShareAttribution.sourceApp,
      utmMedium: ShareAttribution.mediumSocial,
    );
    final landingUrl = attribution.applyTo(
      (publicLinks ?? PublicContentLinkBuilder.fromRuntimeConfig()).postWebUrl(
        surfaceView.postId,
      ),
    );
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
      landingPage: 'work_landing',
      shareId: attribution.shareId,
      title: UITextConstants.contentLabelForKey(profile.titleKey),
      subtitle: UITextConstants.contentLabelForKey(profile.subtitleKey),
      shareTitle: shareSeed.title,
      shareSummary: tagSummary,
      coverUrl: shareSeed.coverUrl,
      actions: const <ContentShareAction>[
        ContentShareAction(id: 'copy_link', label: FoundationText.copyLink),
        ContentShareAction(
          id: 'save_poster',
          label: ChatText.shareActionSavePoster,
        ),
        ContentShareAction(
          id: 'system_share',
          label: ChatText.shareActionSystemShare,
        ),
      ],
      isBlocked: false,
      notice: null,
    );
  }

  /// 分享模板档位只按写入时确定的 [ContentType] 选，不再按已退役的内容身份轴。
  ///
  /// 契约 `shareTemplateProfiles` 目前是空集（identity 档位随 ContentIdentity
  /// 一同退役），档位重新按 ContentType 声明前，端侧按对象类型取默认档位。
  static ShareTemplateProfileConfig _profileForContentType(ContentType type) {
    final declared = ContentUIConfig.shareTemplateProfiles
        .where((profile) => profile.id == type.wireName)
        .toList(growable: false);
    if (declared.isNotEmpty) {
      return declared.first;
    }
    return ShareTemplateProfileConfig(
      id: type.wireName,
      titleKey: 'share_template_work_title',
      subtitleKey: 'share_template_work_subtitle',
      layout: switch (type) {
        ContentType.article => 'article_card',
        ContentType.video => 'video_card',
        ContentType.image => 'image_card',
      },
      coverStrategy: 'post_cover',
      includeAuthor: true,
      includeTimeContext: type != ContentType.article,
      includeTags: true,
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
    switch (view.contentType) {
      case ContentType.article:
        return _ShareSeed(
          title: _clip(title, fallback: ContentText.shareSeedWorkFallbackTitle),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentType.video:
        return _ShareSeed(
          title: _clip(
            body,
            fallback: UITextConstants.shareSeedVideoWorkTitle(displayName),
          ),
          summary: _clip(body, maxLength: 48),
          coverUrl: cover,
        );
      case ContentType.image:
        return _ShareSeed(
          title: _clip(
            body,
            fallback: UITextConstants.shareSeedImageWorkTitle(displayName),
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
