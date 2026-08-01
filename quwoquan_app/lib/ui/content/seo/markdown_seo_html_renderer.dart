import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/media/asset_url_resolver.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/qwq_markdown_ast.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/qwq_markdown_parser.dart';

class SeoHtmlDocument {
  const SeoHtmlDocument({
    required this.html,
    required this.title,
    required this.description,
    required this.canonicalUrl,
    required this.openGraph,
    required this.jsonLd,
    required this.referencedAssetUrls,
    required this.indexable,
  });

  final String html;
  final String title;
  final String description;
  final String canonicalUrl;
  final Map<String, String> openGraph;
  final Map<String, Object?> jsonLd;
  final List<String> referencedAssetUrls;
  final bool indexable;
}

class MarkdownSeoRenderInput {
  const MarkdownSeoRenderInput({
    required this.postId,
    required this.articleMarkdown,
    this.articleMarkdownDigest = '',
    this.articleAssetManifest,
    this.title = '',
    this.summary = '',
    this.coverUrl = '',
    this.authorName = '',
    this.createdAtIso = '',
    this.visibility = 'public',
  });

  final String postId;
  final String articleMarkdown;
  final String articleMarkdownDigest;
  final Map<String, Object?>? articleAssetManifest;
  final String title;
  final String summary;
  final String coverUrl;
  final String authorName;
  final String createdAtIso;
  final String visibility;
}

class MarkdownSeoHtmlRenderer {
  const MarkdownSeoHtmlRenderer({
    QwqMarkdownParser? parser,
    AssetUrlResolver? assetUrlResolver,
  }) : _parser = parser ?? const QwqMarkdownParser(),
       _configuredAssetUrlResolver = assetUrlResolver;

  final QwqMarkdownParser _parser;
  final AssetUrlResolver? _configuredAssetUrlResolver;

  AssetUrlResolver get _assetUrlResolver =>
      _configuredAssetUrlResolver ??
      AssetUrlResolver(
        imageCdnBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
        videoCdnBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
      );

  SeoHtmlDocument render(MarkdownSeoRenderInput input) {
    final canonicalUrl = AppPublicContentLinks.postWebUrl(input.postId);
    final visibility = _visibility(input.visibility);
    if (visibility == _SeoVisibility.private) {
      return SeoHtmlDocument(
        html: '',
        title: input.title.trim(),
        description: '',
        canonicalUrl: canonicalUrl,
        openGraph: const <String, String>{},
        jsonLd: const <String, Object?>{},
        referencedAssetUrls: const <String>[],
        indexable: false,
      );
    }

    final parsed = _parser.parse(input.articleMarkdown).document;
    final assetsById = _assetUrlResolver.resolveManifestVariants(
      input.articleAssetManifest,
    );
    final title = _firstNonEmpty([
      input.title,
      parsed.frontMatter.title,
      _firstHeading(parsed),
      '趣我圈内容',
    ]);
    final description = _firstNonEmpty([
      input.summary,
      parsed.frontMatter.summary,
      _firstParagraph(parsed),
    ]);
    final cover = _firstNonEmpty([
      _resolveRawAssetUrl(input.coverUrl),
      _resolveAssetUrl(parsed.frontMatter.coverAssetId, assetsById),
      _resolveRawAssetUrl(parsed.frontMatter.coverImage),
    ]);
    final buffer = StringBuffer();
    final referenced = <String>{};
    for (final block in parsed.blocks) {
      final rendered = _renderBlock(block, assetsById, referenced);
      if (rendered.isNotEmpty) {
        buffer.writeln(rendered);
      }
    }
    final safeHtml = buffer.toString().trim();
    final openGraph = <String, String>{
      'og:type': 'article',
      'og:title': title,
      'og:description': description,
      'og:url': canonicalUrl,
      if (cover.isNotEmpty) 'og:image': cover,
      'twitter:card': cover.isNotEmpty ? 'summary_large_image' : 'summary',
    };
    final jsonLd = <String, Object?>{
      '@context': 'https://schema.org',
      '@type': 'Article',
      'headline': title,
      'description': description,
      'url': canonicalUrl,
      if (cover.isNotEmpty) 'image': cover,
      if (input.authorName.trim().isNotEmpty)
        'author': <String, Object?>{
          '@type': 'Person',
          'name': input.authorName.trim(),
        },
      if (input.createdAtIso.trim().isNotEmpty)
        'datePublished': input.createdAtIso.trim(),
      if (input.articleMarkdownDigest.trim().isNotEmpty)
        'identifier': input.articleMarkdownDigest.trim(),
    };
    return SeoHtmlDocument(
      html: safeHtml,
      title: title,
      description: description,
      canonicalUrl: canonicalUrl,
      openGraph: openGraph,
      jsonLd: jsonLd,
      referencedAssetUrls: referenced.toList(growable: false),
      indexable: visibility == _SeoVisibility.public,
    );
  }

  String _renderBlock(
    QwqMarkdownBlock block,
    Map<String, MediaAssetVariants> assetsById,
    Set<String> referenced,
  ) {
    switch (block.kind) {
      case QwqMarkdownBlockKind.heading:
        final level = block.level.clamp(1, 3);
        return '<h$level>${_renderInlines(block)}</h$level>';
      case QwqMarkdownBlockKind.paragraph:
        return '<p>${_renderInlines(block)}</p>';
      case QwqMarkdownBlockKind.orderedItem:
        return '<ol><li>${_renderInlines(block)}</li></ol>';
      case QwqMarkdownBlockKind.bulletItem:
        return '<ul><li>${_renderInlines(block)}</li></ul>';
      case QwqMarkdownBlockKind.quote:
        return '<blockquote>${_renderInlines(block)}</blockquote>';
      case QwqMarkdownBlockKind.codeBlock:
        return '<pre><code>${_escape(block.text)}</code></pre>';
      case QwqMarkdownBlockKind.image:
      case QwqMarkdownBlockKind.figure:
        return _renderAssetFigure(block.assetRef, assetsById, referenced);
      case QwqMarkdownBlockKind.gallery:
        final items = block.assetRefs
            .map((ref) => _renderAssetImage(ref, assetsById, referenced))
            .where((html) => html.isNotEmpty)
            .join();
        return items.isEmpty ? '' : '<div class="qwq-gallery">$items</div>';
      case QwqMarkdownBlockKind.callout:
        return '<aside class="qwq-callout">${_renderInlines(block)}</aside>';
      case QwqMarkdownBlockKind.card:
        return '<section class="qwq-card">${_renderInlines(block)}</section>';
      case QwqMarkdownBlockKind.section:
        return '<section>${block.children.map((child) => _renderBlock(child, assetsById, referenced)).join()}</section>';
      case QwqMarkdownBlockKind.spacer:
        return '<div class="qwq-spacer"></div>';
      case QwqMarkdownBlockKind.horizontalRule:
        return '<hr>';
    }
  }

  String _renderAssetFigure(
    QwqMarkdownAssetRef? ref,
    Map<String, MediaAssetVariants> assetsById,
    Set<String> referenced,
  ) {
    if (ref == null) return '';
    final image = _renderAssetImage(ref, assetsById, referenced);
    if (image.isEmpty) return '';
    final caption = ref.caption.trim();
    if (caption.isEmpty) return '<figure>$image</figure>';
    return '<figure>$image<figcaption>${_escape(caption)}</figcaption></figure>';
  }

  String _renderAssetImage(
    QwqMarkdownAssetRef ref,
    Map<String, MediaAssetVariants> assetsById,
    Set<String> referenced,
  ) {
    final url = _resolveAssetUrl(ref.assetId, assetsById);
    if (!_isSafeUrl(url)) return '';
    referenced.add(url);
    final alt = ref.alt.trim().isNotEmpty ? ref.alt : ref.caption;
    return '<img src="${_escapeAttribute(url)}" alt="${_escapeAttribute(alt)}" data-asset-id="${_escapeAttribute(ref.assetId.trim())}">';
  }

  String _renderInlines(QwqMarkdownBlock block) {
    if (block.inlines.isEmpty) return _escape(block.text);
    return block.inlines.map(_renderInline).join();
  }

  String _renderInline(QwqMarkdownInline inline) {
    final text = _escape(inline.text);
    switch (inline.kind) {
      case QwqMarkdownInlineKind.text:
        return text;
      case QwqMarkdownInlineKind.emphasis:
        return '<em>$text</em>';
      case QwqMarkdownInlineKind.strong:
        return '<strong>$text</strong>';
      case QwqMarkdownInlineKind.code:
        return '<code>$text</code>';
      case QwqMarkdownInlineKind.link:
        final href = inline.href.trim();
        if (!_isSafeUrl(href)) return text;
        return '<a href="${_escapeAttribute(href)}" rel="nofollow ugc">$text</a>';
    }
  }

  String _firstHeading(QwqMarkdownDocument doc) {
    for (final block in doc.blocks) {
      if (block.kind == QwqMarkdownBlockKind.heading &&
          block.text.trim().isNotEmpty) {
        return block.text.trim();
      }
    }
    return '';
  }

  String _firstParagraph(QwqMarkdownDocument doc) {
    for (final block in doc.blocks) {
      if (block.kind == QwqMarkdownBlockKind.paragraph &&
          block.text.trim().isNotEmpty) {
        return block.text.trim();
      }
    }
    return '';
  }

  String _firstNonEmpty(Iterable<String> values) {
    return values
        .map((value) => value.trim())
        .firstWhere((value) => value.isNotEmpty, orElse: () => '');
  }

  String _resolveAssetUrl(
    String assetId,
    Map<String, MediaAssetVariants> assetsById,
  ) {
    final id = assetId.trim();
    if (id.isEmpty) return '';
    return assetsById[id]?.urlFor(MediaAssetVariantProfile.display) ?? '';
  }

  String _resolveRawAssetUrl(String raw) {
    final value = raw.trim();
    if (value.isEmpty || value.startsWith('asset://')) {
      return '';
    }
    return _assetUrlResolver.resolveAssetRowUrl(<String, Object?>{
      'cdnUrl': value,
    });
  }

  bool _isSafeUrl(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return false;
    if (trimmed.startsWith('/')) return true;
    final uri = Uri.tryParse(trimmed);
    // 媒体 CDN base 随环境而定（prod 为 https 域名，alpha/本地联调为 http loopback
    // CDN）；只放行 http/https，仍拦截 javascript:/data:/vbscript: 等不安全 scheme。
    return uri != null && (uri.scheme == 'https' || uri.scheme == 'http');
  }

  String _escape(String value) {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
  }

  String _escapeAttribute(String value) => _escape(value);

  _SeoVisibility _visibility(String visibility) {
    final normalized = visibility.trim().toLowerCase();
    switch (normalized) {
      case 'public':
        return _SeoVisibility.public;
      case 'private':
        return _SeoVisibility.private;
    }
    throw ArgumentError.value(
      visibility,
      'visibility',
      'Post visibility must be public or private',
    );
  }
}

enum _SeoVisibility { public, private }
