import 'dart:collection';
import 'dart:math' as math;
import 'dart:ui';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/rendering.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_flow_layout_engine.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/pointer_bridge.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

List<ArticlePageData> resolvePaginatedArticlePages({
  required BuildContext context,
  required BoxConstraints constraints,
  required ArticleDocumentData document,
  required ArticleTemplatePreset template,
  required ArticleFontPreset fontPreset,
  List<ArticlePageData> fallbackPages = const <ArticlePageData>[],
  ArticleCanvasVariant variant = ArticleCanvasVariant.preview,
  double? contentHeightOverride,
}) {
  final visibleTitle = document.titleStyle == ArticleDocumentTitleStyle.none
      ? ''
      : document.title.trim();
  if (visibleTitle.isEmpty &&
      document.body.trim().isEmpty &&
      document.assets.isEmpty &&
      fallbackPages.isNotEmpty) {
    return fallbackPages;
  }
  final preferStructuredFallbackPages = fallbackPages
      .skip(1)
      .any(
        (page) => page.title.trim().isNotEmpty || page.body.trim().isNotEmpty,
      );
  if (preferStructuredFallbackPages) {
    return fallbackPages;
  }
  final metrics = resolveArticleCanvasMetrics(
    context,
    constraints,
    variant: variant,
  );
  final typography = resolveArticleTypography(context, template, fontPreset);
  final stagePadding = articleReaderStagePagePadding();
  final stageWidth = resolveArticlePaperStageWidth(
    context,
    constraints,
    stagePadding: stagePadding,
    allowLandscapeSpread: variant != ArticleCanvasVariant.editor,
  );
  final viewportSliceHeight =
      contentHeightOverride ??
      metrics.contentSizeForStageWidth(stageWidth).height;
  final pages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
    document: document,
    metrics: metrics,
    stageWidth: stageWidth,
    titleStyle: typography.titleStyle,
    bodyStyle: typography.bodyStyle,
    viewportSliceHeight: viewportSliceHeight,
  );
  if (pages.isNotEmpty) {
    return pages;
  }
  return fallbackPages;
}

class ArticlePageShell extends StatelessWidget {
  const ArticlePageShell({
    super.key,
    required this.template,
    required this.fontPreset,
    required this.pageIndex,
    required this.totalPages,
    required this.child,
    this.aspectRatio = 0.72,
    this.outerPadding,
    this.contentPadding,
    this.headerReservedHeight,
    this.footerReservedHeight,
    this.showIndicator = true,
    this.variant = ArticlePageShellVariant.book,
    this.headerLabel,
    this.footerLabel,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final int pageIndex;
  final int totalPages;
  final Widget child;
  final double aspectRatio;
  final EdgeInsets? outerPadding;
  final EdgeInsets? contentPadding;
  final double? headerReservedHeight;
  final double? footerReservedHeight;
  final bool showIndicator;
  final ArticlePageShellVariant variant;
  final String? headerLabel;
  final String? footerLabel;

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(context, template);
    final headerText = headerLabel?.trim() ?? '';
    final footerText = footerLabel?.trim() ?? '';
    final resolvedOuterPadding =
        outerPadding ?? EdgeInsets.all(AppSpacing.containerSm);
    final resolvedContentPadding =
        contentPadding ??
        EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
        );
    final resolvedHeaderHeight =
        headerReservedHeight ??
        AppSpacing.sm + AppSpacing.hairline + AppSpacing.intraGroupSm * 2;
    final resolvedFooterHeight =
        footerReservedHeight ??
        AppSpacing.sm + AppSpacing.hairline + AppSpacing.interGroupSm;

    Widget buildPageContent({required bool expandBody}) {
      final content = <Widget>[
        if (headerText.isNotEmpty) ...<Widget>[
          Text(
            headerText,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: palette.secondaryTextColor.withValues(alpha: 0.86),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: palette.paperBorderColor.withValues(alpha: 0.5),
                  width: AppSpacing.hairline,
                ),
              ),
            ),
            child: SizedBox(height: AppSpacing.hairline),
          ),
          SizedBox(height: math.max(0, resolvedHeaderHeight - AppSpacing.sm)),
        ],
        if (expandBody) Expanded(child: child) else child,
        if (footerText.isNotEmpty) ...<Widget>[
          SizedBox(height: math.max(0, resolvedFooterHeight - AppSpacing.sm)),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: palette.paperBorderColor.withValues(alpha: 0.5),
                  width: AppSpacing.hairline,
                ),
              ),
            ),
            child: SizedBox(height: AppSpacing.hairline),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Align(
            alignment: Alignment.center,
            child: Text(
              footerText,
              style: TextStyle(
                color: palette.secondaryTextColor.withValues(alpha: 0.86),
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      ];
      return Padding(
        padding: resolvedContentPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: expandBody ? MainAxisSize.max : MainAxisSize.min,
          children: content,
        ),
      );
    }

    Widget buildFlatPaper({
      required bool showShadow,
      required double borderAlpha,
    }) {
      Widget paper = DecoratedBox(
        decoration: BoxDecoration(
          color: palette.paperColor,
          border: Border(
            top: BorderSide(
              color: palette.paperBorderColor.withValues(alpha: borderAlpha),
              width: AppSpacing.hairline,
            ),
            left: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha * 0.72,
              ),
              width: AppSpacing.hairline,
            ),
            right: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha * 0.72,
              ),
              width: AppSpacing.hairline,
            ),
            bottom: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha + 0.08,
              ),
              width: AppSpacing.hairline,
            ),
          ),
          boxShadow: showShadow
              ? <BoxShadow>[
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.18),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ]
              : null,
        ),
        child: buildPageContent(expandBody: true),
      );
      if (template == ArticleTemplatePreset.journal) {
        paper = CustomPaint(
          foregroundPainter: _JournalPaperTexturePainter(palette),
          child: paper,
        );
      }
      return Padding(padding: resolvedOuterPadding, child: paper);
    }

    if (variant == ArticlePageShellVariant.plainEdit ||
        variant == ArticlePageShellVariant.readerSheet) {
      final paper = buildFlatPaper(
        showShadow: variant == ArticlePageShellVariant.readerSheet,
        borderAlpha: variant == ArticlePageShellVariant.readerSheet
            ? 0.16
            : 0.24,
      );
      final sheet = AspectRatio(aspectRatio: aspectRatio, child: paper);
      if (!showIndicator) {
        return sheet;
      }
      return Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          sheet,
          Positioned(
            top: resolvedOuterPadding.top + AppSpacing.intraGroupXs,
            right: resolvedOuterPadding.right + AppSpacing.intraGroupXs,
            child: _ArticlePageIndicator(
              label: '${pageIndex + 1}/$totalPages',
              palette: palette,
            ),
          ),
        ],
      );
    }

    Widget paper = DecoratedBox(
      decoration: BoxDecoration(
        color: palette.paperColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: palette.paperBorderColor,
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: palette.shadowColor,
            blurRadius: 24,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: buildPageContent(expandBody: true),
    );

    if (template == ArticleTemplatePreset.journal) {
      paper = ClipPath(
        clipper: const _JournalPaperClipper(),
        child: DecoratedBox(
          decoration: BoxDecoration(
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: palette.shadowColor,
                blurRadius: 26,
                offset: const Offset(0, 16),
              ),
            ],
          ),
          child: CustomPaint(
            foregroundPainter: _JournalPaperTexturePainter(palette),
            child: paper,
          ),
        ),
      );
    } else {
      paper = ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        child: paper,
      );
    }

    return AspectRatio(
      aspectRatio: aspectRatio,
      child: Stack(
        children: <Widget>[
          Positioned.fill(
            child: _ArticleBackdrop(template: template, palette: palette),
          ),
          Positioned.fill(
            child: Padding(
              padding: resolvedOuterPadding,
              child: IgnorePointer(
                child: CustomPaint(
                  painter: _ArticleBookChromePainter(
                    template: template,
                    palette: palette,
                    pageIndex: pageIndex,
                    totalPages: totalPages,
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Padding(padding: resolvedOuterPadding, child: paper),
          ),
          if (showIndicator)
            Positioned(
              top: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              child: _ArticlePageIndicator(
                label: '${pageIndex + 1}/$totalPages',
                palette: palette,
              ),
            ),
        ],
      ),
    );
  }
}

class ArticlePageReadOnlyView extends StatelessWidget {
  const ArticlePageReadOnlyView({
    super.key,
    required this.page,
    required this.template,
    required this.fontPreset,
    this.metrics,
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetrics? metrics;

  @override
  Widget build(BuildContext context) {
    final typography = resolveArticleTypography(context, template, fontPreset);
    return Align(
      alignment: Alignment.topLeft,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: _buildReadOnlyPageFragments(
          context,
          page,
          typography,
          template,
          metrics ?? ArticleCanvasMetrics.snapshot(),
        ),
      ),
    );
  }
}

List<ArticleLayoutFragment> _resolveReadOnlyFragments(ArticlePageData page) {
  if (page.fragments.isNotEmpty) {
    return page.fragments;
  }
  final fragments = <ArticleLayoutFragment>[];
  if (page.title.trim().isNotEmpty) {
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.title,
        text: page.title.trim(),
        textStyleKey: 'title',
      ),
    );
  }
  for (final block in page.contentBlocks) {
    if (block.type == ArticleDocumentBlockType.image &&
        block.imageUrl.trim().isNotEmpty) {
      fragments.add(
        ArticleLayoutFragment(
          kind:
              block.imageLayout == 'wrapLeft' ||
                  block.imageLayout == 'wrapRight'
              ? ArticleLayoutFragmentKind.wrapContent
              : ArticleLayoutFragmentKind.fullWidthImage,
          text: page.body.trim(),
          asset: ArticleDocumentAsset(
            id: block.id,
            offset: block.offset,
            imageUrl: block.imageUrl,
            imageLayout: block.imageLayout,
            caption: block.caption,
          ),
        ),
      );
      continue;
    }
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.semanticBlock,
        block: block,
        text: block.text.trim(),
        textStyleKey: switch (block.type) {
          ArticleDocumentBlockType.heading2 => 'heading2',
          ArticleDocumentBlockType.heading3 => 'heading3',
          ArticleDocumentBlockType.sectionTitle => 'sectionTitle',
          ArticleDocumentBlockType.orderedItem => 'orderedItem',
          ArticleDocumentBlockType.bulletItem => 'bulletItem',
          _ => 'body',
        },
        textAlign: block.textAlign,
      ),
    );
  }
  if (page.imageUrl.trim().isNotEmpty &&
      !fragments.any((fragment) => fragment.hasAsset)) {
    fragments.add(
      ArticleLayoutFragment(
        kind: page.usesWrappedLayout
            ? ArticleLayoutFragmentKind.wrapContent
            : ArticleLayoutFragmentKind.fullWidthImage,
        text: page.body.trim(),
        asset: ArticleDocumentAsset(
          id: '${page.id}_asset',
          offset: 0,
          imageUrl: page.imageUrl,
          imageLayout: page.imageLayout,
          caption: page.caption,
        ),
      ),
    );
    if (!page.usesWrappedLayout && page.body.trim().isNotEmpty) {
      fragments.add(
        ArticleLayoutFragment(
          kind: ArticleLayoutFragmentKind.body,
          text: page.body.trim(),
          textStyleKey: 'body',
        ),
      );
    }
  } else if (page.body.trim().isNotEmpty &&
      !fragments.any(
        (fragment) =>
            fragment.kind == ArticleLayoutFragmentKind.body ||
            fragment.kind == ArticleLayoutFragmentKind.wrapContent,
      )) {
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.body,
        text: page.body.trim(),
        textStyleKey: 'body',
      ),
    );
  }
  return fragments;
}

List<Widget> _buildReadOnlyPageFragments(
  BuildContext context,
  ArticlePageData page,
  ArticleTypographySpec typography,
  ArticleTemplatePreset template,
  ArticleCanvasMetrics metrics,
) {
  final fragments = _resolveReadOnlyFragments(page);
  final widgets = <Widget>[];
  final spacing = articleSpacingResolver();
  for (var index = 0; index < fragments.length; index += 1) {
    final fragment = fragments[index];
    final nextFragment = index + 1 < fragments.length
        ? fragments[index + 1]
        : null;
    var appended = false;
    switch (fragment.kind) {
      case ArticleLayoutFragmentKind.title:
        widgets.add(Text(fragment.text.trim(), style: typography.titleStyle));
        appended = true;
        break;
      case ArticleLayoutFragmentKind.semanticBlock:
        if (fragment.block == null) {
          break;
        }
        widgets.add(
          _ArticleSemanticBlock(block: fragment.block!, typography: typography),
        );
        appended = true;
        break;
      case ArticleLayoutFragmentKind.fullWidthImage:
        if (!fragment.hasAsset) {
          break;
        }
        widgets.add(
          _ArticlePageImage(
            imageUrl: fragment.asset!.imageUrl.trim(),
            borderRadius: 0,
            aspectRatio: fragment.asset!.imageLayout == 'journalCard'
                ? metrics.journalImageAspectRatio
                : metrics.fullWidthImageAspectRatio,
          ),
        );
        if (fragment.asset!.caption.trim().isNotEmpty) {
          widgets.add(
            SizedBox(
              height: spacing.between(
                ArticleSpacingSemantic.figure,
                ArticleSpacingSemantic.caption,
              ),
            ),
          );
          widgets.add(
            Center(
              child: Text(
                fragment.asset!.caption.trim(),
                textAlign: TextAlign.center,
                style: typography.captionStyle,
              ),
            ),
          );
        }
        appended = true;
        break;
      case ArticleLayoutFragmentKind.wrapContent:
        if (!fragment.hasAsset) {
          break;
        }
        widgets.add(
          ArticleWrappedParagraph(
            imageUrl: fragment.asset!.imageUrl.trim(),
            body: fragment.text.trim(),
            imageLayout: fragment.asset!.imageLayout,
            caption: fragment.asset!.caption,
            metrics: metrics,
          ),
        );
        appended = true;
        break;
      case ArticleLayoutFragmentKind.body:
        if (fragment.text.trim().isNotEmpty) {
          widgets.add(Text(fragment.text.trim(), style: typography.bodyStyle));
          appended = true;
        }
        break;
    }
    if (!appended || nextFragment == null) {
      continue;
    }
    final prevSemantic = articleSpacingSemanticForFragment(fragment);
    final nextSemantic = articleSpacingSemanticForFragment(nextFragment);
    final double gap;
    if (prevSemantic == ArticleSpacingSemantic.figure &&
        nextSemantic == ArticleSpacingSemantic.figure) {
      gap = spacing.betweenConsecutiveFigures();
    } else {
      gap = spacing.between(prevSemantic, nextSemantic);
    }
    if (gap > 0) {
      widgets.add(SizedBox(height: gap));
    }
  }
  return widgets;
}

class ArticleFrontispieceView extends StatelessWidget {
  const ArticleFrontispieceView({
    super.key,
    required this.page,
    required this.template,
    required this.fontPreset,
    required this.coverUrl,
    this.imageKey = const ValueKey<String>('article-frontispiece-image'),
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String coverUrl;
  final Key imageKey;

  @override
  Widget build(BuildContext context) {
    const coverTitleLineHeight = 1.15;
    final typography = resolveArticleTypography(context, template, fontPreset);
    final frontispieceBody = _resolvedBodyText();
    final coverTitle = page.title.trim();
    return LayoutBuilder(
      builder: (context, constraints) {
        final coverHeight = math.min(
          constraints.maxHeight * 0.3,
          constraints.maxWidth /
              (template == ArticleTemplatePreset.journal ? 0.8 : 1.1),
        );
        return Align(
          alignment: Alignment.topLeft,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox(
                height: coverHeight,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    ArticleAdaptiveImage(key: imageKey, imageUrl: coverUrl),
                    Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: <Color>[
                              AppColors.black.withValues(alpha: 0.04),
                              AppColors.black.withValues(alpha: 0.18),
                              AppColors.black.withValues(alpha: 0.74),
                            ],
                            stops: const <double>[0.0, 0.48, 1.0],
                          ),
                        ),
                      ),
                    ),
                    if (coverTitle.isNotEmpty)
                      Positioned(
                        left: AppSpacing.containerMd,
                        right: AppSpacing.containerMd,
                        bottom: AppSpacing.containerMd,
                        child: Text(
                          coverTitle,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: typography.titleStyle.copyWith(
                            color: AppColors.white,
                            height: coverTitleLineHeight,
                            shadows: const <Shadow>[
                              Shadow(
                                color: AppColors.overlayLight,
                                blurRadius: 18,
                                offset: Offset(0, 4),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              SizedBox(height: AppSpacing.containerMd),
              if (frontispieceBody.isNotEmpty)
                Text(frontispieceBody, style: typography.bodyStyle),
            ],
          ),
        );
      },
    );
  }

  String _resolvedBodyText() {
    final body = page.body.trim();
    if (body.isNotEmpty) {
      return body;
    }
    return page.contentBlocks
        .where((block) => block.isTextLike && block.hasText)
        .map((block) => block.text.trim())
        .where((value) => value.isNotEmpty)
        .join('\n');
  }
}

enum ArticleReaderFallbackReason {
  forcedDegradedPager,
  pageCurlDisabled,
  accessibilityDisableAnimations,
  longDocument,
}

@immutable
class ArticleReaderPageFlipCommit {
  const ArticleReaderPageFlipCommit({
    required this.fromPage,
    required this.toPage,
    required this.durationMs,
    required this.mechanism,
  });

  final int fromPage;
  final int toPage;
  final int durationMs;
  final String mechanism;

  String get direction => toPage >= fromPage ? 'forward' : 'backward';
}

@immutable
class ArticleReaderPageCurlAbort {
  const ArticleReaderPageCurlAbort({
    required this.corner,
    required this.progress,
  });

  final String corner;
  final double progress;
}

class ArticleReadOnlyBookDeck extends StatefulWidget {
  const ArticleReadOnlyBookDeck({
    super.key,
    required this.pages,
    required this.template,
    required this.fontPreset,
    required this.metrics,
    this.coverUrl = '',
    this.initialPage = 0,
    this.pagePadding = EdgeInsets.zero,
    this.enablePageCurl = true,
    this.forceDegradedPager = false,
    this.onPageChanged,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
  });

  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetrics metrics;
  final String coverUrl;
  final int initialPage;
  final EdgeInsets pagePadding;
  final bool enablePageCurl;
  final bool forceDegradedPager;
  final ValueChanged<int>? onPageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;

  @override
  State<ArticleReadOnlyBookDeck> createState() =>
      _ArticleReadOnlyBookDeckState();
}

class _ArticleReadOnlyBookDeckState extends State<ArticleReadOnlyBookDeck>
    with SingleTickerProviderStateMixin {
  static const bool _isFlutterTest = bool.fromEnvironment('FLUTTER_TEST');
  static const double _overflowSwitchVelocity = 320;
  static const double _overflowSwitchDistance = AppSpacing.buttonHeight;

  bool get _disableAdvancedPageCurlForTest {
    final bindingName = WidgetsBinding.instance.runtimeType.toString();
    return _isFlutterTest || bindingName.contains('TestWidgetsFlutterBinding');
  }

  late final PageController _pageController;
  late final AnimationController _pageFlipAnimationController;
  late final StPageFlipPointerBridge _pointerBridge;
  StPageFlipController? _pageFlipController;
  StPageFlipAnimationPlan? _activePageFlipAnimation;
  Offset? _pointerDownLocalPosition;
  Offset? _dragStartGlobalPosition;
  Offset? _latestDragGlobalPosition;
  DateTime? _dragStartedAt;
  int _lastAnimationFrameIndex = -1;
  double _edgeOverflowDistance = 0;
  StPageFlipDirection? _pendingOverflowDirection;
  bool _overflowTriggered = false;
  bool _overflowLocked = false;
  late int _currentPage;
  DateTime? _pageTransitionStartedAt;
  String? _pageTransitionMechanism;
  ArticleReaderFallbackReason? _reportedFallbackReason;
  final Map<String, Widget> _pageSurfaceCache = <String, Widget>{};
  final Map<int, GlobalKey> _pageTextureBoundaryKeys = <int, GlobalKey>{};
  final Map<int, ArticlePageTextureSnapshot> _pageTextureSnapshots =
      <int, ArticlePageTextureSnapshot>{};
  final ListQueue<int> _pendingTexturePages = ListQueue<int>();
  final ArticlePageCurlMeshBuilder _curlMeshBuilder =
      const ArticlePageCurlMeshBuilder();
  ArticlePageTextureSession? _activeTextureSession;
  Size? _cachedSurfaceSize;
  ui.FragmentProgram? _lightingShaderProgram;
  ui.FragmentProgram? _backfaceShaderProgram;
  bool _snapshotCaptureScheduled = false;

  int get _safeInitialPage {
    if (widget.pages.isEmpty) {
      return 0;
    }
    return widget.initialPage.clamp(0, widget.pages.length - 1).toInt();
  }

  ArticleReaderFallbackReason? get _fallbackReason {
    final disableAnimations = WidgetsBinding
        .instance
        .platformDispatcher
        .accessibilityFeatures
        .disableAnimations;
    if (widget.forceDegradedPager) {
      return ArticleReaderFallbackReason.forcedDegradedPager;
    }
    if (!widget.enablePageCurl) {
      return ArticleReaderFallbackReason.pageCurlDisabled;
    }
    if (disableAnimations) {
      return ArticleReaderFallbackReason.accessibilityDisableAnimations;
    }
    if (widget.pages.length > 18) {
      return ArticleReaderFallbackReason.longDocument;
    }
    return null;
  }

  bool get _useDegradedPager {
    return _fallbackReason != null;
  }

  bool get _showsPageCurl => !_useDegradedPager && widget.pages.length > 1;

  @override
  void initState() {
    super.initState();
    _currentPage = _safeInitialPage;
    _pageController = PageController(initialPage: _currentPage);
    _pointerBridge = StPageFlipPointerBridge();
    _pageFlipAnimationController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 260),
            lowerBound: 0,
            upperBound: 1,
          )
          ..addListener(_handlePageFlipAnimationTick)
          ..addStatusListener(_handlePageFlipAnimationStatus);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onPageChanged?.call(_currentPage);
    });
    _maybeReportFallbackReason();
    _preloadPageCurlShaders();
  }

  @override
  void didUpdateWidget(covariant ArticleReadOnlyBookDeck oldWidget) {
    super.didUpdateWidget(oldWidget);
    _maybeReportFallbackReason();
    if (widget.pages != oldWidget.pages ||
        widget.template != oldWidget.template ||
        widget.fontPreset != oldWidget.fontPreset ||
        widget.metrics != oldWidget.metrics ||
        widget.coverUrl != oldWidget.coverUrl) {
      _pageSurfaceCache.clear();
      _resetPageTextureSnapshots();
      _clearActiveTextureSession();
    }
    final nextInitialPage = _safeInitialPage;
    if (widget.initialPage != oldWidget.initialPage &&
        nextInitialPage != _currentPage) {
      if (_useDegradedPager && _pageController.hasClients) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || !_pageController.hasClients) {
            return;
          }
          _pageController.jumpToPage(nextInitialPage);
          setState(() {
            _currentPage = nextInitialPage;
          });
        });
      } else {
        setState(() {
          _currentPage = nextInitialPage;
          _pageFlipController?.setCurrentPage(_currentPage);
        });
      }
    } else if (_currentPage >= widget.pages.length && widget.pages.isNotEmpty) {
      if (_useDegradedPager) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || !_pageController.hasClients) {
            return;
          }
          final lastPage = widget.pages.length - 1;
          _pageController.jumpToPage(lastPage);
          setState(() {
            _currentPage = lastPage;
          });
        });
      } else {
        setState(() {
          _currentPage = widget.pages.length - 1;
          _pageFlipController?.setCurrentPage(_currentPage);
        });
      }
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    _pageFlipAnimationController.dispose();
    _pointerBridge.dispose();
    _disposePageTextureSnapshots();
    _clearActiveTextureSession();
    super.dispose();
  }

  void _maybeReportFallbackReason() {
    final reason = _fallbackReason;
    if (reason == null || reason == _reportedFallbackReason) {
      return;
    }
    _reportedFallbackReason = reason;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      widget.onFallbackResolved?.call(reason);
    });
  }

  StPageFlipScene? get _pageFlipScene => _pageFlipController?.scene;

  Size _resolvePageSizeForStage(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - widget.pagePadding.horizontal,
    );
    final pageWidth = availableWidth >= 920
        ? ((availableWidth - resolveArticleReaderStageSpec().spineShadowWidth) /
                  2)
              .clamp(1.0, availableWidth)
              .toDouble()
        : availableWidth;
    final pageHeight = pageWidth / widget.metrics.aspectRatio;
    return Size(pageWidth, pageHeight);
  }

  void _configurePageFlipController(Size stageSize) {
    if (widget.pages.isEmpty) {
      _pageFlipController = null;
      _pageSurfaceCache.clear();
      _cachedSurfaceSize = null;
      _resetPageTextureSnapshots();
      _clearActiveTextureSession();
      return;
    }
    final pageSize = _resolvePageSizeForStage(stageSize);
    if (_cachedSurfaceSize != pageSize) {
      _cachedSurfaceSize = pageSize;
      _pageSurfaceCache.clear();
      _resetPageTextureSnapshots();
      _clearActiveTextureSession();
    }
    final layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
    );
    final spreadModel = StPageFlipSpreadModel(
      pageCount: widget.pages.length,
      showCover: widget.coverUrl.trim().isNotEmpty,
    );
    if (_pageFlipController == null) {
      _pageFlipController = StPageFlipController(
        spreadModel: spreadModel,
        layout: layout,
        initialPage: _currentPage,
      );
      return;
    }
    _pageFlipController!.updateConfiguration(
      spreadModel: spreadModel,
      layout: layout,
      currentPage: _currentPage,
    );
  }

  Future<void> _preloadPageCurlShaders() async {
    if (_disableAdvancedPageCurlForTest) {
      return;
    }
    try {
      final lighting = await ui.FragmentProgram.fromAsset(
        'shaders/article_page_curl_lighting.frag',
      );
      final backface = await ui.FragmentProgram.fromAsset(
        'shaders/article_page_curl_backface.frag',
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _lightingShaderProgram = lighting;
        _backfaceShaderProgram = backface;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || widget.pages.isEmpty) {
          return;
        }
        _queuePageTextureSnapshots(<int>{
          _currentPage,
          _currentPage - 1,
          _currentPage + 1,
        }, prioritize: true);
      });
    } catch (e, st) {
      if (kDebugMode) {
        debugPrint('ArticleReadOnlyBookDeck: page curl shaders failed to load: $e');
        debugPrintStack(stackTrace: st);
      }
    }
  }

  void _disposePageTextureSnapshots() {
    for (final snapshot in _pageTextureSnapshots.values) {
      snapshot.dispose();
    }
    _pageTextureSnapshots.clear();
    _pendingTexturePages.clear();
    _pageTextureBoundaryKeys.clear();
  }

  void _resetPageTextureSnapshots() {
    _disposePageTextureSnapshots();
    _snapshotCaptureScheduled = false;
    _clearActiveTextureSession();
  }

  double _pageTexturePixelRatio(BuildContext context) {
    final view = View.maybeOf(context);
    final pixelRatio =
        view?.devicePixelRatio ??
        MediaQuery.maybeOf(context)?.devicePixelRatio ??
        1.0;
    return pixelRatio.clamp(1.0, 2.0).toDouble();
  }

  void _queuePageTextureSnapshots(
    Iterable<int> pageIndices, {
    bool prioritize = false,
  }) {
    if (_disableAdvancedPageCurlForTest) {
      return;
    }
    var added = false;
    final orderedIndices = pageIndices.toList(growable: false);
    final iteration = prioritize ? orderedIndices.reversed : orderedIndices;
    for (final index in iteration) {
      if (index < 0 || index >= widget.pages.length) {
        continue;
      }
      if (_pageTextureSnapshots.containsKey(index)) {
        continue;
      }
      final alreadyPending = _pendingTexturePages.contains(index);
      if (alreadyPending && !prioritize) {
        continue;
      }
      _pendingTexturePages.remove(index);
      if (prioritize) {
        _pendingTexturePages.addFirst(index);
      } else {
        _pendingTexturePages.addLast(index);
      }
      added = added || !alreadyPending;
      _pageTextureBoundaryKeys.putIfAbsent(
        index,
        () => GlobalKey(debugLabel: 'article_page_texture_$index'),
      );
    }
    if (added) {
      _schedulePendingTextureCapture();
    }
  }

  bool _shouldFreezeTextureSession(StPageFlipScene scene) {
    return _activePageFlipAnimation != null ||
        scene.state != StPageFlipState.read;
  }

  void _schedulePendingTextureCapture() {
    if (_snapshotCaptureScheduled || _pendingTexturePages.isEmpty || !mounted) {
      return;
    }
    _snapshotCaptureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _snapshotCaptureScheduled = false;
      await _capturePendingPageTextures();
    });
  }

  Future<void> _capturePendingPageTextures() async {
    if (!mounted || _pendingTexturePages.isEmpty) {
      return;
    }
    final pending = _pendingTexturePages.take(3).toList(growable: false);
    var capturedAny = false;
    for (final index in pending) {
      final boundaryKey = _pageTextureBoundaryKeys[index];
      final boundaryContext = boundaryKey?.currentContext;
      final boundary =
          boundaryContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null ||
          !boundary.hasSize ||
          boundary.size.isEmpty ||
          boundary.debugNeedsPaint) {
        continue;
      }
      try {
        final image = await boundary.toImage(
          pixelRatio: _pageTexturePixelRatio(boundaryContext!),
        );
        if (!mounted) {
          image.dispose();
          return;
        }
        _pageTextureSnapshots[index]?.dispose();
        _pageTextureSnapshots[index] = ArticlePageTextureSnapshot(
          image: image,
          logicalSize: boundary.size,
          pixelRatio: _pageTexturePixelRatio(boundaryContext),
        );
        _pendingTexturePages.remove(index);
        capturedAny = true;
      } catch (_) {
        // Texture capture failed; will retry next cycle.
      }
    }
    if (capturedAny && mounted) {
      final scene = _pageFlipScene;
      if (scene != null) {
        _syncActiveTextureSession(scene);
      }
      setState(() {});
    }
    if (_pendingTexturePages.isNotEmpty) {
      _schedulePendingTextureCapture();
    }
  }

  bool _supportsAdvancedPageCurl(StPageFlipScene scene) {
    return !_disableAdvancedPageCurlForTest &&
        _lightingShaderProgram != null &&
        _backfaceShaderProgram != null;
  }

  ArticlePageTextureBinding? _textureBindingForScene(StPageFlipScene scene) {
    return resolveArticlePageTextureBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      bottomPageIndex: scene.bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  ArticlePageTextureBundle? _textureBundleForBinding(
    ArticlePageTextureBinding binding, {
    ArticlePageTextureBundle? fallback,
  }) {
    final recto = _pageTextureSnapshots[binding.rectoPageIndex];
    final verso = _pageTextureSnapshots[binding.versoPageIndex];
    final bottom = _pageTextureSnapshots[binding.bottomPageIndex];
    if (recto == null || verso == null || bottom == null) {
      return fallback;
    }
    return ArticlePageTextureBundle(recto: recto, verso: verso, bottom: bottom);
  }

  void _syncActiveTextureSession(StPageFlipScene scene) {
    final binding = _textureBindingForScene(scene);
    final existing = _activeTextureSession;
    final sameBinding =
        binding != null &&
        existing != null &&
        existing.binding.matches(binding);
    final resolvedBundle = binding == null
        ? null
        : _textureBundleForBinding(
            binding,
            fallback: sameBinding ? existing.bundle : null,
          );
    final nextSession = resolveArticlePageTextureSession(
      existing: existing,
      binding: binding,
      resolvedBundle: resolvedBundle,
      supportsHighFidelity: _supportsAdvancedPageCurl(scene),
      freezeBinding: _shouldFreezeTextureSession(scene),
    );
    if (nextSession == null) {
      _activeTextureSession = null;
      return;
    }
    _queuePageTextureSnapshots(
      nextSession.binding.prioritizedPageIndices,
      prioritize: true,
    );
    _activeTextureSession = nextSession.copyWith(
      bundle: _textureBundleForBinding(
        nextSession.binding,
        fallback: nextSession.bundle,
      ),
    );
  }

  void _clearActiveTextureSession() {
    _activeTextureSession = null;
  }

  ArticlePageTextureBundle? _resolveHighFidelityTextureBundle(
    StPageFlipScene scene,
  ) {
    final session = _activeTextureSession;
    final binding = _textureBindingForScene(scene);
    if (session == null ||
        binding == null ||
        !session.binding.matches(binding) ||
        !session.preferHighFidelity) {
      return null;
    }
    return _textureBundleForBinding(binding, fallback: session.bundle);
  }

  Path _buildBottomClipPath(StPageFlipScene scene) {
    final calculation = scene.calculation;
    final direction = scene.direction;
    final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final pageRectPath = Path()..addRect(pageRect);
    if (calculation == null || direction == null) {
      return pageRectPath;
    }
    final area = calculation.getBottomClipArea();
    if (area.length < 3) {
      return pageRectPath;
    }
    final polygon = _localPolygonFromArea(
      area: area,
      anchor: calculation.getBottomPagePosition(),
      angle: 0,
      direction: direction,
    );
    final position = convertBookPointToViewport(
      calculation.getBottomPagePosition(),
      scene.layout.bounds,
      direction: direction,
    );
    final path = Path()
      ..moveTo(position.dx + polygon.first.dx, position.dy + polygon.first.dy);
    for (final point in polygon.skip(1)) {
      path.lineTo(position.dx + point.dx, position.dy + point.dy);
    }
    path.close();
    return Path.combine(PathOperation.intersect, pageRectPath, path);
  }

  ArticlePageCurlRenderScene? _tryBuildHighFidelityRenderScene(
    BuildContext context,
    StPageFlipScene scene,
    Size stageSize,
    Size pageSize,
  ) {
    if (!_supportsAdvancedPageCurl(scene)) {
      return null;
    }
    final calculation = scene.calculation;
    final session = _activeTextureSession;
    final direction = scene.direction;
    final corner = scene.corner;
    final binding = _textureBindingForScene(scene);
    if (calculation == null ||
        direction == null ||
        corner == null ||
        binding == null ||
        session == null ||
        !session.binding.matches(binding) ||
        !session.preferHighFidelity) {
      return null;
    }
    _queuePageTextureSnapshots(binding.requiredPageIndices);
    final textures = _resolveHighFidelityTextureBundle(scene);
    if (textures == null) {
      return null;
    }
    final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final progress = ((calculation.getFlippingProgress()) / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    final meshFrame = _curlMeshBuilder.build(
      pageRect: pageRect,
      pageSize: pageSize,
      dragPoint: calculation.getPosition(),
      progress: progress,
      direction: direction,
      corner: corner,
      bottomClipPath: _buildBottomClipPath(scene),
      reversePose: null,
    );
    final palette = resolveArticleTemplatePalette(context, widget.template);
    final lightState = resolveArticlePageCurlLightState(
      progress: progress,
      foldXNormalized: meshFrame.foldXNormalized,
      curlLift: meshFrame.curlLift,
      rollProgress: meshFrame.rollProgress,
      cylinderProgress: meshFrame.cylinderProgress,
      unfoldProgress: meshFrame.unfoldProgress,
      cylinderRadiusNormalized: 0,
      unrollWidthNormalized: 0,
      bottomGapNormalized: 0,
      direction: direction,
      corner: corner,
    );
    final lightConfig = ArticlePageCurlLightConfig(
      shadowColor: palette.shadowColor.withValues(alpha: 0.82),
      highlightColor: AppColors.white.withValues(alpha: 0.22),
      paperTintColor: Color.alphaBlend(
        AppColors.white.withValues(alpha: 0.14),
        palette.paperColor,
      ).withValues(alpha: 0.24),
      ambientOcclusionColor: AppColors.black.withValues(alpha: 0.22),
    );
    return ArticlePageCurlRenderScene(
      stageSize: stageSize,
      pageRect: pageRect,
      textures: textures,
      meshFrame: meshFrame,
      lightConfig: lightConfig,
      lightState: lightState,
      direction: direction,
      corner: corner,
    );
  }

  Widget _buildPageTextureCaptureLayer(BuildContext context, Size pageSize) {
    if (_disableAdvancedPageCurlForTest || _pendingTexturePages.isEmpty) {
      return const SizedBox.shrink();
    }
    final capturePages = _pendingTexturePages.take(3).toList(growable: false);
    return _StableTextureCaptureLayer(
      key: const ValueKey<String>('texture_capture_layer'),
      capturePages: capturePages,
      pageSize: pageSize,
      boundaryKeys: _pageTextureBoundaryKeys,
      buildPage: (index) => _buildPageSurfaceWidget(context, index, pageSize),
    );
  }

  Widget _buildCachedPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize, {
    required _ArticlePageSurfaceKind kind,
  }) {
    final cacheKey =
        '${kind.name}:$pageIndex:${pageSize.width.toStringAsFixed(2)}:${pageSize.height.toStringAsFixed(2)}:${widget.template.name}:${widget.fontPreset.name}:${widget.coverUrl.trim().isNotEmpty ? 1 : 0}';
    return _pageSurfaceCache.putIfAbsent(cacheKey, () {
      switch (kind) {
        case _ArticlePageSurfaceKind.front:
        case _ArticlePageSurfaceKind.bottom:
          return _buildReaderPage(context, pageIndex, pageSize);
        case _ArticlePageSurfaceKind.back:
          return _buildOpaqueBackPageSurface(context, pageIndex, pageSize);
      }
    });
  }

  Widget _buildOpaqueBackPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize,
  ) {
    final palette = resolveArticleTemplatePalette(context, widget.template);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            Color.alphaBlend(
              AppColors.white.withValues(alpha: 0.22),
              palette.paperColor,
            ),
            palette.paperColor,
            Color.alphaBlend(
              palette.paperBorderColor.withValues(alpha: 0.12),
              palette.paperColor,
            ),
          ],
        ),
        border: Border.all(
          color: palette.paperBorderColor.withValues(alpha: 0.22),
          width: AppSpacing.hairline,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          ColoredBox(color: palette.paperColor),
          IgnorePointer(
            child: Opacity(
              opacity: 0.72,
              child: _buildMirroredReaderPage(context, pageIndex, pageSize),
            ),
          ),
          IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.white.withValues(alpha: 0.14),
                    AppColors.transparent,
                    palette.shadowColor.withValues(alpha: 0.06),
                  ],
                  stops: const <double>[0.0, 0.42, 1.0],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _handlePageFlipAnimationTick() {
    final controller = _pageFlipController;
    final plan = _activePageFlipAnimation;
    if (controller == null || plan == null || plan.frames.isEmpty || !mounted) {
      return;
    }
    final maxIndex = plan.frames.length - 1;
    final nextIndex = maxIndex == 0
        ? 0
        : (_pageFlipAnimationController.value * maxIndex).round().clamp(
            0,
            maxIndex,
          );
    if (nextIndex == _lastAnimationFrameIndex) {
      return;
    }
    controller.applyAnimationFrame(
      plan.frames[nextIndex],
      reversePose: null,
    );
    _syncActiveTextureSession(controller.scene);
    _lastAnimationFrameIndex = nextIndex;
    setState(() {});
  }

  void _handlePageFlipAnimationStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed) {
      return;
    }
    final controller = _pageFlipController;
    final plan = _activePageFlipAnimation;
    if (controller == null || plan == null) {
      return;
    }
    final previousPage = controller.currentPageIndex;
    controller.completeAnimation(plan);
    _activePageFlipAnimation = null;
    _lastAnimationFrameIndex = -1;
    if (plan.needReset) {
      _clearActiveTextureSession();
    } else {
      _syncActiveTextureSession(controller.scene);
    }
    final nextPage = controller.currentPageIndex;
    if (!mounted) {
      return;
    }
    setState(() {
      _currentPage = nextPage;
    });
    if (plan.isTurned) {
      widget.onPageChanged?.call(_currentPage);
      _emitPageFlipCommit(fromPage: previousPage, toPage: _currentPage);
    }
  }

  void _runPageFlipAnimation(
    StPageFlipAnimationPlan plan, {
    bool reportAbort = false,
  }) {
    if (reportAbort) {
      _emitPageCurlAbortForPlan(plan);
    }
    final scene = _pageFlipScene;
    if (scene != null) {
      _syncActiveTextureSession(scene);
    }
    _activePageFlipAnimation = plan;
    _lastAnimationFrameIndex = -1;
    _pageFlipAnimationController.duration = plan.duration;
    _pageFlipAnimationController.forward(from: 0);
  }

  void _triggerOverflow(StPageFlipDirection direction) {
    if (_overflowTriggered) {
      return;
    }
    _overflowTriggered = true;
    if (direction == StPageFlipDirection.forward) {
      widget.onOverflowNext?.call();
    } else {
      widget.onOverflowPrevious?.call();
    }
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  void _trackEdgeOverflow(Offset delta, StPageFlipDirection direction) {
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += delta.dx.abs();
    if (_edgeOverflowDistance >= _overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
  }

  bool _shouldCommitPageFlip({
    required StPageFlipController controller,
    required StPageFlipDirection direction,
    required double progress,
    required Velocity velocity,
    Offset? dragStart,
    Offset? dragLatest,
    DateTime? dragStartedAt,
  }) {
    final directionSign = direction == StPageFlipDirection.forward ? -1.0 : 1.0;
    final directionalVelocity = velocity.pixelsPerSecond.dx * directionSign;
    final directionalDistance = dragStart != null && dragLatest != null
        ? (dragLatest.dx - dragStart.dx) * directionSign
        : 0.0;
    final dragRatio = (directionalDistance / controller.layout.bounds.pageWidth)
        .clamp(0.0, 1.0)
        .toDouble();
    final elapsedMs = dragStartedAt == null
        ? 0
        : DateTime.now().difference(dragStartedAt).inMilliseconds;
    final crossedMidpoint = progress > 0.44;
    final sustainedPull = dragRatio > 0.24;
    final deliberateCornerLift = progress > 0.14 && dragRatio > 0.08;
    final deliberateDrag = progress > 0.2 && dragRatio > 0.16;
    final decisiveVelocity = directionalVelocity > 260;
    final quickLift =
        elapsedMs > 0 && elapsedMs < 420 && dragRatio > 0.06 && progress > 0.12;
    final assistedSnap = deliberateCornerLift && directionalVelocity > 120;
    return crossedMidpoint ||
        sustainedPull ||
        deliberateDrag ||
        decisiveVelocity ||
        quickLift ||
        assistedSnap;
  }

  String _cornerNameFromPageFlip(
    StPageFlipCorner corner,
    StPageFlipDirection direction,
  ) {
    if (corner == StPageFlipCorner.top) {
      return direction == StPageFlipDirection.forward
          ? 'top_right'
          : 'top_left';
    }
    return direction == StPageFlipDirection.forward
        ? 'bottom_right'
        : 'bottom_left';
  }

  void _emitPageCurlAbortForPlan(StPageFlipAnimationPlan plan) {
    final calculation = _pageFlipScene?.calculation;
    final progress = ((calculation?.getFlippingProgress() ?? 0) / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    _clearPageTransition();
    if (progress <= 0) {
      return;
    }
    widget.onPageCurlAborted?.call(
      ArticleReaderPageCurlAbort(
        corner: _cornerNameFromPageFlip(plan.corner, plan.direction),
        progress: progress,
      ),
    );
  }

  void _handleStageTapUp(TapUpDetails details) {
    if (!_showsPageCurl || _activePageFlipAnimation != null) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.flip(details.localPosition);
    if (plan == null) {
      return;
    }
    _startPageTransition('page_curl');
    setState(() {});
    _runPageFlipAnimation(plan);
  }

  void _handleStagePanStart(Offset localPosition) {
    if (!_showsPageCurl || _activePageFlipAnimation != null) {
      return;
    }
    final startPosition = _pointerDownLocalPosition ?? localPosition;
    _dragStartGlobalPosition = startPosition;
    _latestDragGlobalPosition = localPosition;
    _dragStartedAt = DateTime.now();
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final direction = controller.directionForGlobalPoint(startPosition);
    if (!controller.canFlipDirection(direction)) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
      return;
    }
    _startPageTransition('page_curl');
    controller.fold(startPosition);
    if ((localPosition - startPosition).distance > 0) {
      controller.fold(localPosition);
    }
    _syncActiveTextureSession(controller.scene);
    setState(() {});
  }

  void _handleStagePanUpdate(Offset localPosition, Offset delta) {
    if (!_showsPageCurl || _activePageFlipAnimation != null) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    _latestDragGlobalPosition = localPosition;
    final direction = controller.directionForGlobalPoint(localPosition);
    if (!controller.canFlipDirection(direction)) {
      _trackEdgeOverflow(delta, direction);
      return;
    }
    controller.fold(localPosition);
    _syncActiveTextureSession(controller.scene);
    setState(() {});
  }

  void _handleStagePanCancel() {
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    _resetOverflowTracking();
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    controller.cancelInteraction();
    _clearActiveTextureSession();
    setState(() {});
  }

  void _handleStagePanEnd(Velocity velocity) {
    final controller = _pageFlipController;
    final dragStart = _dragStartGlobalPosition;
    final dragLatest = _latestDragGlobalPosition;
    final dragStartedAt = _dragStartedAt;
    _pointerDownLocalPosition = null;
    _dragStartGlobalPosition = null;
    _latestDragGlobalPosition = null;
    _dragStartedAt = null;
    if (controller == null) {
      _resetOverflowTracking();
      return;
    }
    if (dragStart != null) {
      final direction = controller.directionForGlobalPoint(dragStart);
      if (!controller.canFlipDirection(direction)) {
        final velocityX = velocity.pixelsPerSecond.dx;
        if (!_overflowTriggered && velocityX.abs() >= _overflowSwitchVelocity) {
          _triggerOverflow(direction);
        }
        _resetOverflowTracking();
        return;
      }
    }

    var plan = controller.stopMove();
    _resetOverflowTracking();
    if (plan == null) {
      controller.cancelInteraction();
      _clearActiveTextureSession();
      setState(() {});
      return;
    }
    if (!plan.isTurned) {
      final direction =
          controller.scene.direction ??
          (dragStart != null
              ? controller.directionForGlobalPoint(dragStart)
              : StPageFlipDirection.forward);
      final corner =
          controller.scene.corner ??
          (dragStart != null
              ? controller.cornerForGlobalPoint(dragStart)
              : StPageFlipCorner.bottom);
      final progress =
          ((controller.scene.calculation?.getFlippingProgress() ?? 0) / 100)
              .clamp(0.0, 1.0)
              .toDouble();
      final shouldCommit = _shouldCommitPageFlip(
        controller: controller,
        direction: direction,
        progress: progress,
        velocity: velocity,
        dragStart: dragStart,
        dragLatest: dragLatest,
        dragStartedAt: dragStartedAt,
      );
      if (shouldCommit) {
        plan = direction == StPageFlipDirection.forward
            ? controller.flipNext(corner)
            : controller.flipPrev(corner);
      }
    }
    if (plan == null) {
      controller.cancelInteraction();
      _clearActiveTextureSession();
      setState(() {});
      return;
    }
    if (!plan.isTurned) {
      _runPageFlipAnimation(plan, reportAbort: true);
    } else {
      _runPageFlipAnimation(plan);
    }
  }

  void _handleStageMouseHover(PointerHoverEvent event) {
    if (!_showsPageCurl || _activePageFlipAnimation != null) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.showCorner(event.localPosition);
    if (plan != null) {
      _runPageFlipAnimation(plan);
      return;
    }
    _syncActiveTextureSession(controller.scene);
    setState(() {});
  }

  void _handleStageMouseExit(PointerExitEvent event) {
    if (!_showsPageCurl || _activePageFlipAnimation != null) {
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      return;
    }
    final plan = controller.showCorner(const Offset(-1, -1));
    if (plan != null) {
      _runPageFlipAnimation(plan);
      return;
    }
    controller.cancelInteraction();
    _clearActiveTextureSession();
    setState(() {});
  }

  void _handleStagePointerDown(PointerDownEvent event) {
    if (!_showsPageCurl) {
      return;
    }
    _pointerDownLocalPosition = event.localPosition;
    _pointerBridge.handleTouchStart(event.localPosition, () {});
  }

  void _handleStagePointerMove(PointerMoveEvent event) {
    if (!_showsPageCurl || _dragStartGlobalPosition != null) {
      return;
    }
    _pointerBridge.handleTouchMove(event.localPosition, () {});
  }

  void _handleStagePointerUp(PointerUpEvent event) {
    _pointerDownLocalPosition = null;
    if (!_showsPageCurl || _dragStartGlobalPosition != null) {
      _pointerBridge.cancel();
      return;
    }
    final controller = _pageFlipController;
    if (controller == null) {
      _pointerBridge.cancel();
      return;
    }
    final swipe = _pointerBridge.handleTouchEnd(
      event.localPosition,
      pageHeight: controller.layout.bounds.height,
    );
    if (swipe == null || !controller.canFlipDirection(swipe.direction)) {
      return;
    }
    final plan = swipe.direction == StPageFlipDirection.forward
        ? controller.flipNext(swipe.corner)
        : controller.flipPrev(swipe.corner);
    if (plan == null) {
      return;
    }
    _startPageTransition('page_curl');
    _runPageFlipAnimation(plan);
  }

  void _handleStagePointerCancel(PointerCancelEvent event) {
    _pointerDownLocalPosition = null;
    _pointerBridge.cancel();
    _clearActiveTextureSession();
  }

  void _startPageTransition(String mechanism) {
    _pageTransitionStartedAt = DateTime.now();
    _pageTransitionMechanism = mechanism;
  }

  void _clearPageTransition() {
    _pageTransitionStartedAt = null;
    _pageTransitionMechanism = null;
  }

  void _emitPageFlipCommit({required int fromPage, required int toPage}) {
    final startedAt = _pageTransitionStartedAt;
    final mechanism = _pageTransitionMechanism;
    _clearPageTransition();
    if (startedAt == null || mechanism == null || fromPage == toPage) {
      return;
    }
    widget.onPageFlipCommitted?.call(
      ArticleReaderPageFlipCommit(
        fromPage: fromPage,
        toPage: toPage,
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        mechanism: mechanism,
      ),
    );
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollStartNotification &&
        notification.dragDetails != null &&
        _pageTransitionStartedAt == null) {
      _startPageTransition(_useDegradedPager ? 'book_style_pager' : 'pager');
    } else if (notification is OverscrollNotification && !_overflowLocked) {
      if (notification.overscroll < 0) {
        _overflowLocked = true;
        widget.onOverflowPrevious?.call();
      } else if (notification.overscroll > 0) {
        _overflowLocked = true;
        widget.onOverflowNext?.call();
      }
    } else if (notification is ScrollEndNotification) {
      _overflowLocked = false;
      if (_pageFlipScene?.calculation == null) {
        _clearPageTransition();
      }
    }
    return false;
  }

  Key _hotzoneKey(_ArticlePageCurlCorner corner) {
    return switch (corner) {
      _ArticlePageCurlCorner.topLeft => TestKeys.articlePageCurlHotzoneTopLeft,
      _ArticlePageCurlCorner.topRight =>
        TestKeys.articlePageCurlHotzoneTopRight,
      _ArticlePageCurlCorner.bottomLeft =>
        TestKeys.articlePageCurlHotzoneBottomLeft,
      _ArticlePageCurlCorner.bottomRight =>
        TestKeys.articlePageCurlHotzoneBottomRight,
    };
  }

  Rect _pageRectForStage(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - widget.pagePadding.horizontal,
    );
    final availableHeight = math.max(
      1.0,
      stageSize.height - widget.pagePadding.vertical,
    );
    final pageWidth = math.min(
      availableWidth,
      availableHeight * widget.metrics.aspectRatio,
    );
    final pageHeight = pageWidth / widget.metrics.aspectRatio;
    final left = (stageSize.width - pageWidth) / 2;
    final minTop = widget.pagePadding.top;
    final maxTop = math.max(
      minTop,
      stageSize.height - widget.pagePadding.bottom - pageHeight,
    );
    final preferredTop = (stageSize.height - pageHeight) / 2;
    final top = preferredTop.clamp(minTop, maxTop).toDouble();
    return Rect.fromLTWH(left, top, pageWidth, pageHeight);
  }

  Widget _buildPageSurfaceWidget(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    final page = widget.pages[index];
    return ArticlePageShell(
      template: widget.template,
      fontPreset: widget.fontPreset,
      pageIndex: index,
      totalPages: widget.pages.length,
      aspectRatio: widget.metrics.aspectRatio,
      outerPadding: widget.metrics.outerPadding,
      contentPadding: widget.metrics.contentPadding,
      headerReservedHeight: widget.metrics.headerReservedHeight,
      footerReservedHeight: widget.metrics.footerReservedHeight,
      variant: ArticlePageShellVariant.readerSheet,
      showIndicator: false,
      footerLabel: '${index + 1}/${widget.pages.length}',
      child: index == 0 && widget.coverUrl.trim().isNotEmpty
          ? ArticleFrontispieceView(
              page: page,
              template: widget.template,
              fontPreset: widget.fontPreset,
              coverUrl: widget.coverUrl.trim(),
            )
          : ArticlePageReadOnlyView(
              page: page,
              template: widget.template,
              fontPreset: widget.fontPreset,
              metrics: widget.metrics,
            ),
    );
  }

  Widget _buildReaderPage(BuildContext context, int index, Size pageSize) {
    return SizedBox(
      width: pageSize.width,
      height: pageSize.height,
      child: RepaintBoundary(
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildMirroredReaderPage(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    return Transform.flip(
      flipX: true,
      child: SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildFlippingSurfaceOverlay({
    required ArticleTemplatePalette palette,
    required StPageFlipDirection direction,
    required double progress,
    required bool showBackside,
  }) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    final lift = Curves.easeOutCubic.transform(settledProgress);
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final shadowColor = palette.shadowColor.withValues(
      alpha: (showBackside ? 0.06 : 0.12) + (lift * 0.08),
    );
    final tunnelAlpha = (showBackside ? 0.06 : 0.08) + (lift * 0.06);
    final tunnelColor = AppColors.black.withValues(
      alpha: tunnelAlpha.clamp(0.0, 1.0).toDouble(),
    );
    final highlightColor = AppColors.white.withValues(
      alpha: (showBackside ? 0.08 : 0.14) + (lift * 0.08),
    );
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: showBackside ? 0.1 : 0.16),
                  AppColors.transparent,
                  tunnelColor,
                ],
                stops: const <double>[0.0, 0.5, 1.0],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: edgeAlignment,
                end: oppositeEdge,
                colors: <Color>[
                  shadowColor,
                  palette.paperBorderColor.withValues(
                    alpha: 0.08 + lift * 0.06,
                  ),
                  AppColors.transparent,
                ],
                stops: const <double>[0.0, 0.28, 0.9],
              ),
            ),
          ),
          Align(
            alignment: edgeAlignment,
            child: FractionallySizedBox(
              widthFactor: (showBackside ? 0.12 : 0.08) + (lift * 0.04),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: edgeAlignment,
                    end: oppositeEdge,
                    colors: <Color>[highlightColor, AppColors.transparent],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSoftFlippingPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    required double progress,
  }) {
    final palette = resolveArticleTemplatePalette(context, widget.template);
    // 前翻：翻过 8% 后显示背面（镜像内容），模拟纸张翻转后看到背面。
    // 后翻：始终显示正面——后翻展示的是上一页的正面内容。
    final showBackside =
        direction == StPageFlipDirection.forward && progress > 0.08;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (showBackside)
          _buildCachedPageSurface(
            context,
            pageIndex,
            pageSize,
            kind: _ArticlePageSurfaceKind.back,
          ),
        if (!showBackside)
          _buildCachedPageSurface(
            context,
            pageIndex,
            pageSize,
            kind: _ArticlePageSurfaceKind.front,
          ),
        _buildFlippingSurfaceOverlay(
          palette: palette,
          direction: direction,
          progress: progress,
          showBackside: showBackside,
        ),
      ],
    );
  }

  Widget _buildBottomProjectedPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    StPageFlipShadowData? shadow,
  }) {
    final palette = resolveArticleTemplatePalette(context, widget.template);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        _buildCachedPageSurface(
          context,
          pageIndex,
          pageSize,
          kind: _ArticlePageSurfaceKind.bottom,
        ),
        if (shadow != null)
          _buildBottomPageProjectionOverlay(
            shadow: shadow,
            direction: direction,
            pageSize: pageSize,
            palette: palette,
          ),
        IgnorePointer(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: 0.05),
                  AppColors.transparent,
                  palette.shadowColor.withValues(alpha: 0.03),
                ],
                stops: const <double>[0.0, 0.36, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBottomPageProjectionOverlay({
    required StPageFlipShadowData shadow,
    required StPageFlipDirection direction,
    required Size pageSize,
    required ArticleTemplatePalette palette,
  }) {
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final widthFactor =
        (math.max(shadow.width, pageSize.width * 0.12) / pageSize.width)
            .clamp(0.12, 0.72)
            .toDouble();
    return IgnorePointer(
      child: Transform.rotate(
        angle: shadow.angle * 0.18,
        alignment: edgeAlignment,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            Align(
              alignment: edgeAlignment,
              child: FractionallySizedBox(
                widthFactor: widthFactor,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: edgeAlignment,
                      end: oppositeEdge,
                      colors: <Color>[
                        AppColors.black.withValues(
                          alpha: shadow.opacity * 0.26,
                        ),
                        palette.shadowColor.withValues(
                          alpha: shadow.opacity * 0.14,
                        ),
                        AppColors.transparent,
                      ],
                      stops: const <double>[0.0, 0.32, 1.0],
                    ),
                  ),
                ),
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.black.withValues(alpha: shadow.opacity * 0.03),
                    AppColors.transparent,
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  _ArticlePageCurlCorner? _stageCornerForScene(StPageFlipScene scene) {
    final direction = scene.direction;
    final corner = scene.corner;
    if (direction == null || corner == null || scene.calculation == null) {
      return null;
    }
    return switch ((direction, corner)) {
      (StPageFlipDirection.forward, StPageFlipCorner.top) =>
        _ArticlePageCurlCorner.topRight,
      (StPageFlipDirection.forward, StPageFlipCorner.bottom) =>
        _ArticlePageCurlCorner.bottomRight,
      (StPageFlipDirection.back, StPageFlipCorner.top) =>
        _ArticlePageCurlCorner.topLeft,
      (StPageFlipDirection.back, StPageFlipCorner.bottom) =>
        _ArticlePageCurlCorner.bottomLeft,
    };
  }

  List<Offset> _localPolygonFromArea({
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    // 前翻和后翻用同样的变换：相对于 anchor 平移 + 旋转。
    // 坐标镜像已经在 convertViewportPointToPage / convertBookPointToViewport
    // 层完成，这里不需要再做 X 轴镜像。
    return area
        .map((point) {
          final translated =
              Offset(point.dx - anchor.dx, point.dy - anchor.dy);
          return rotatePoint(translated, Offset.zero, angle);
        })
        .toList(growable: false);
  }

  Widget _buildStaticBookPage(BuildContext context, int pageIndex, Rect rect) {
    return Positioned.fromRect(
      rect: rect,
      child: _buildCachedPageSurface(
        context,
        pageIndex,
        rect.size,
        kind: _ArticlePageSurfaceKind.front,
      ),
    );
  }

  Widget _buildSoftPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
    required StPageFlipBoundsRect bounds,
    bool isFlippingPage = false,
    double progress = 0,
    StPageFlipShadowData? projectedShadow,
  }) {
    final polygon = _localPolygonFromArea(
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
    );
    final position = convertBookPointToViewport(
      anchor,
      bounds,
      direction: direction,
    );
    return Positioned(
      left: position.dx,
      top: position.dy,
      width: pageSize.width,
      height: pageSize.height,
      child: Transform.rotate(
        angle: angle,
        alignment: Alignment.topLeft,
        child: ClipPath(
          clipper: _ArticlePolygonClipper(polygon),
          child: isFlippingPage
              ? _buildSoftFlippingPageSurface(
                  context: context,
                  pageIndex: pageIndex,
                  pageSize: pageSize,
                  direction: direction,
                  progress: progress,
                )
              : _buildBottomProjectedPageSurface(
                  context: context,
                  pageIndex: pageIndex,
                  pageSize: pageSize,
                  direction: direction,
                  shadow: projectedShadow,
                ),
        ),
      ),
    );
  }

  Widget _buildHardFlippingPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipScene scene,
    required StPageFlipDirection direction,
  }) {
    final progress = scene.calculation?.getFlippingProgress() ?? 0;
    final hardAngle = direction == StPageFlipDirection.forward
        ? (90 * (200 - progress * 2)) / 100
        : (-90 * (200 - progress * 2)) / 100;
    final isRightPage =
        !(direction == StPageFlipDirection.forward &&
            scene.layout.orientation != StPageFlipOrientation.portrait);
    final pageRect = resolveBookPageRect(
      scene.layout,
      isRightPage: isRightPage,
    );
    return Positioned.fromRect(
      rect: pageRect,
      child: Transform(
        alignment: isRightPage ? Alignment.topLeft : Alignment.topRight,
        transform: Matrix4.identity()
          ..setEntry(3, 2, 0.002)
          ..rotateY(hardAngle * math.pi / 180),
        child: _buildCachedPageSurface(
          context,
          pageIndex,
          pageSize,
          kind: _ArticlePageSurfaceKind.front,
        ),
      ),
    );
  }

  Widget _buildDynamicPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipScene scene,
    required StPageFlipDirection direction,
    required StPageFlipDensity density,
    required bool isFlippingPage,
  }) {
    // hard density 页面走硬纸翻页路径（前翻和回翻均适用）。
    if (density == StPageFlipDensity.hard && isFlippingPage) {
      return _buildHardFlippingPageLayer(
        context: context,
        pageIndex: pageIndex,
        pageSize: pageSize,
        scene: scene,
        direction: direction,
      );
    }
    return _buildSoftPageLayer(
      context: context,
      pageIndex: pageIndex,
      pageSize: pageSize,
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
      bounds: scene.layout.bounds,
      isFlippingPage: isFlippingPage,
      progress: ((scene.calculation?.getFlippingProgress() ?? 0) / 100)
          .clamp(0.0, 1.0)
          .toDouble(),
      projectedShadow: isFlippingPage ? null : scene.shadow,
    );
  }

  Widget _buildHotzoneMarkers(StPageFlipScene scene, Size stageSize) {
    const hotzoneExtent = 88.0;
    final rightPageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final leftAnchorRect =
        scene.layout.orientation == StPageFlipOrientation.portrait
        ? rightPageRect
        : resolveBookPageRect(scene.layout, isRightPage: false);
    final markerOffsets = <_ArticlePageCurlCorner, Offset>{
      _ArticlePageCurlCorner.topLeft: Offset(
        leftAnchorRect.left
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        leftAnchorRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      _ArticlePageCurlCorner.topRight: Offset(
        (rightPageRect.right - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        rightPageRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      _ArticlePageCurlCorner.bottomLeft: Offset(
        leftAnchorRect.left
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (leftAnchorRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      _ArticlePageCurlCorner.bottomRight: Offset(
        (rightPageRect.right - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (rightPageRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
    };
    return Stack(
      children: markerOffsets.entries
          .map((entry) {
            final hotzoneRect = Rect.fromLTWH(
              entry.value.dx,
              entry.value.dy,
              hotzoneExtent,
              hotzoneExtent,
            );
            return Positioned(
              left: hotzoneRect.left,
              top: hotzoneRect.top,
              width: hotzoneRect.width,
              height: hotzoneRect.height,
              child: IgnorePointer(
                child: SizedBox.expand(key: _hotzoneKey(entry.key)),
              ),
            );
          })
          .toList(growable: false),
    );
  }

  Widget _buildDegradedReaderStage(BuildContext context, Rect pageRect) {
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        CustomPaint(
          painter: _ArticleReaderStagePainter(
            palette: resolveArticleTemplatePalette(context, widget.template),
            pageRect: pageRect,
            pageCount: widget.pages.length,
          ),
        ),
        NotificationListener<ScrollNotification>(
          onNotification: _handleScrollNotification,
          child: PageView.builder(
            key: TestKeys.articleBookStylePager,
            controller: _pageController,
            itemCount: widget.pages.length,
            onPageChanged: (index) {
              final previousPage = _currentPage;
              setState(() {
                _currentPage = index;
              });
              _emitPageFlipCommit(fromPage: previousPage, toPage: index);
              widget.onPageChanged?.call(index);
            },
            itemBuilder: (context, index) {
              return Align(
                alignment: Alignment.topCenter,
                child: Padding(
                  padding: EdgeInsets.only(top: pageRect.top),
                  child: _buildReaderPage(context, index, pageRect.size),
                ),
              );
            },
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: _ArticleBookStylePagerHintPainter(
                resolveArticleTemplatePalette(context, widget.template),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildInteractiveReaderStage(BuildContext context, Size stageSize) {
    _configurePageFlipController(stageSize);
    final scene = _pageFlipScene;
    if (scene == null) {
      return const SizedBox.shrink();
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final bookRect = scene.layout.bounds.rect;
    final calculation = scene.calculation;
    final progress = ((calculation?.getFlippingProgress() ?? 0) / 100)
        .clamp(0.0, 1.0)
        .toDouble();
    _queuePageTextureSnapshots(<int>{
      scene.currentPageIndex,
      scene.currentPageIndex - 1,
      scene.currentPageIndex + 1,
    });
    final highFidelityScene = _tryBuildHighFidelityRenderScene(
      context,
      scene,
      stageSize,
      pageSize,
    );
    final activeBinding = _activeTextureSession?.binding;
    final highFidelityRenderedPages = highFidelityScene == null
        ? const <int>{}
        : (activeBinding?.requiredPageIndices ?? const <int>{});
    final layers = <Widget>[
      RepaintBoundary(
        child: CustomPaint(
          painter: _ArticleReaderStagePainter(
            palette: resolveArticleTemplatePalette(context, widget.template),
            pageRect: bookRect,
            pageCount: widget.pages.length,
            activeCorner: _stageCornerForScene(scene),
            progress: progress,
          ),
        ),
      ),
    ];

    final leftPageIndex = scene.visibleSpread.leftPageIndex;
    final rightPageIndex = scene.visibleSpread.rightPageIndex;
    if (leftPageIndex != null &&
        !highFidelityRenderedPages.contains(leftPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          leftPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: false),
        ),
      );
    }
    if (rightPageIndex != null &&
        !highFidelityRenderedPages.contains(rightPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          rightPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: true),
        ),
      );
    }

    final direction = scene.direction;
    if (highFidelityScene != null) {
      layers.add(
        Positioned.fill(
          child: ArticlePageCurlRenderer(
            scene: highFidelityScene,
            lightingProgram: _lightingShaderProgram,
            backfaceProgram: _backfaceShaderProgram,
          ),
        ),
      );
    } else {
      if (calculation != null &&
          direction != null &&
          scene.bottomPageIndex != null) {
        layers.add(
          _buildDynamicPageLayer(
            context: context,
            pageIndex: scene.bottomPageIndex!,
            pageSize: pageSize,
            area: calculation.getBottomClipArea(),
            anchor: calculation.getBottomPagePosition(),
            angle: 0,
            scene: scene,
            direction: direction,
            density:
                scene.flippingPageDensity ??
                scene.bottomPageDensity ??
                StPageFlipDensity.soft,
            isFlippingPage: false,
          ),
        );
      }

      if (calculation != null &&
          direction != null &&
          scene.flippingPageIndex != null) {
        layers.add(
          _buildDynamicPageLayer(
            context: context,
            pageIndex: scene.flippingPageIndex!,
            pageSize: pageSize,
            area: calculation.getFlippingClipArea(),
            anchor: calculation.getActiveCorner(),
            angle: calculation.getAngle(),
            scene: scene,
            direction: direction,
            density: scene.flippingPageDensity ?? StPageFlipDensity.soft,
            isFlippingPage: true,
          ),
        );
      }
    }

    layers.add(
      Positioned.fill(
        key: TestKeys.articlePageCurlLayer,
        child: _buildHotzoneMarkers(scene, stageSize),
      ),
    );
    if (_pendingTexturePages.isNotEmpty) {
      layers.add(
        Positioned.fill(
          child: _buildPageTextureCaptureLayer(context, pageSize),
        ),
      );
    }

    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: _handleStagePointerDown,
      onPointerMove: _handleStagePointerMove,
      onPointerUp: _handleStagePointerUp,
      onPointerCancel: _handleStagePointerCancel,
      child: MouseRegion(
        onHover: _handleStageMouseHover,
        onExit: _handleStageMouseExit,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapUp: _handleStageTapUp,
          onPanStart: (details) => _handleStagePanStart(details.localPosition),
          onPanUpdate: (details) =>
              _handleStagePanUpdate(details.localPosition, details.delta),
          onPanCancel: _handleStagePanCancel,
          onPanEnd: (details) => _handleStagePanEnd(details.velocity),
          child: Stack(fit: StackFit.expand, children: layers),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final stageSize = Size(
          constraints.maxWidth.isFinite ? constraints.maxWidth : 1,
          constraints.maxHeight.isFinite ? constraints.maxHeight : 1,
        );
        final pageRect = _pageRectForStage(stageSize);
        if (_useDegradedPager) {
          return _buildDegradedReaderStage(context, pageRect);
        }
        return _buildInteractiveReaderStage(context, stageSize);
      },
    );
  }
}

enum _ArticlePageCurlCorner { topLeft, topRight, bottomLeft, bottomRight }

enum _ArticlePageSurfaceKind { front, back, bottom }

class ArticleTemplateThumbnail extends StatelessWidget {
  const ArticleTemplateThumbnail({
    super.key,
    required this.template,
    required this.fontPreset,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final borderColor = selected
        ? AppColors.primaryColor
        : CupertinoColors.separator.resolveFrom(context);

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            width: AppSpacing.avatarUserXl,
            height: AppSpacing.oneHundred + AppSpacing.xs,
            padding: const EdgeInsets.all(AppSpacing.two),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: borderColor, width: selected ? 2 : 1),
            ),
            child: ArticlePageShell(
              template: template,
              fontPreset: fontPreset,
              pageIndex: 0,
              totalPages: 1,
              aspectRatio: 72 / 104,
              outerPadding: const EdgeInsets.all(AppSpacing.two),
              showIndicator: false,
              contentPadding: const EdgeInsets.fromLTRB(8, 10, 8, 8),
              headerReservedHeight: 0,
              footerReservedHeight: 0,
              child: _TemplatePreviewFiller(
                template: template,
                fontPreset: fontPreset,
                label: label,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              color: CupertinoColors.label.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: selected
                  ? AppTypography.semiBold
                  : AppTypography.medium,
            ),
          ),
        ],
      ),
    );
  }
}

@immutable
class ArticleTemplatePalette {
  const ArticleTemplatePalette({
    required this.stageBackground,
    required this.paperColor,
    required this.paperBorderColor,
    required this.textColor,
    required this.secondaryTextColor,
    required this.accentColor,
    required this.badgeBackground,
    required this.badgeTextColor,
    required this.shadowColor,
    required this.overlayColor,
  });

  final Color stageBackground;
  final Color paperColor;
  final Color paperBorderColor;
  final Color textColor;
  final Color secondaryTextColor;
  final Color accentColor;
  final Color badgeBackground;
  final Color badgeTextColor;
  final Color shadowColor;
  final Color overlayColor;
}

ArticleTemplatePalette resolveArticleTemplatePalette(
  BuildContext context,
  ArticleTemplatePreset template,
) {
  final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

  switch (template) {
    case ArticleTemplatePreset.ritual:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.ritualStageDark
            : ArticleTemplateColors.ritualStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.ritualPaperDark
            : ArticleTemplateColors.ritualPaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.ritualPaperBorderDark
            : ArticleTemplateColors.ritualPaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.ritualTextDark
            : ArticleTemplateColors.ritualTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.ritualSecondaryTextDark
            : ArticleTemplateColors.ritualSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.ritualAccentDark
            : ArticleTemplateColors.ritualAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.ritualBadgeBackgroundDark
            : ArticleTemplateColors.ritualBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.ritualBadgeTextDark
            : ArticleTemplateColors.ritualBadgeTextLight,
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.36 : 0.12),
        overlayColor: isDark
            ? ArticleTemplateColors.ritualOverlayDark
            : ArticleTemplateColors.ritualOverlayLight,
      );
    case ArticleTemplatePreset.diffuse:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.diffuseStageDark
            : ArticleTemplateColors.diffuseStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.diffusePaperDark
            : ArticleTemplateColors.diffusePaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.diffusePaperBorderDark
            : ArticleTemplateColors.diffusePaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.diffuseTextDark
            : ArticleTemplateColors.diffuseTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.diffuseSecondaryTextDark
            : ArticleTemplateColors.diffuseSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.diffuseAccentDark
            : ArticleTemplateColors.diffuseAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.diffuseBadgeBackgroundDark
            : ArticleTemplateColors.diffuseBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.diffuseBadgeTextDark
            : ArticleTemplateColors.diffuseBadgeTextLight,
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.34 : 0.11),
        overlayColor: isDark
            ? ArticleTemplateColors.diffuseOverlayDark
            : ArticleTemplateColors.diffuseOverlayLight,
      );
    case ArticleTemplatePreset.journal:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.journalStageDark
            : ArticleTemplateColors.journalStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.journalPaperDark
            : ArticleTemplateColors.journalPaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.journalPaperBorderDark
            : ArticleTemplateColors.journalPaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.journalTextDark
            : ArticleTemplateColors.journalTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.journalSecondaryTextDark
            : ArticleTemplateColors.journalSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.journalAccentDark
            : ArticleTemplateColors.journalAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.journalBadgeBackgroundDark
            : ArticleTemplateColors.journalBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.journalBadgeTextDark
            : ArticleTemplateColors.journalBadgeTextLight,
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.14),
        overlayColor: isDark
            ? ArticleTemplateColors.journalOverlayDark
            : ArticleTemplateColors.journalOverlayLight,
      );
    case ArticleTemplatePreset.tech:
      return ArticleTemplatePalette(
        stageBackground: ArticleTemplateColors.techStage,
        paperColor: ArticleTemplateColors.techPaper,
        paperBorderColor: ArticleTemplateColors.techPaperBorder,
        textColor: ArticleTemplateColors.techText,
        secondaryTextColor: ArticleTemplateColors.techSecondaryText,
        accentColor: ArticleTemplateColors.techAccent,
        badgeBackground: ArticleTemplateColors.techBadgeBackground,
        badgeTextColor: ArticleTemplateColors.techBadgeText,
        shadowColor: AppColors.black.withValues(alpha: 0.42),
        overlayColor: ArticleTemplateColors.techOverlay,
      );
    case ArticleTemplatePreset.gentle:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.gentleStageDark
            : ArticleTemplateColors.gentleStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.gentlePaperDark
            : ArticleTemplateColors.gentlePaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.gentlePaperBorderDark
            : ArticleTemplateColors.gentlePaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.gentleTextDark
            : ArticleTemplateColors.gentleTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.gentleSecondaryTextDark
            : ArticleTemplateColors.gentleSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.gentleAccentDark
            : ArticleTemplateColors.gentleAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.gentleBadgeBackgroundDark
            : ArticleTemplateColors.gentleBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.gentleBadgeTextDark
            : ArticleTemplateColors.gentleBadgeTextLight,
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: isDark
            ? ArticleTemplateColors.gentleOverlayDark
            : ArticleTemplateColors.gentleOverlayLight,
      );
  }
}

/// 纸张质感 → 色板映射（替代 resolveArticleTemplatePalette）。
ArticleTemplatePalette resolveArticlePaperPalette(
  BuildContext context,
  ArticlePaperTexture texture,
) {
  final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

  Color paper(Color light, Color dark) => isDark ? dark : light;
  Color text(Color light, Color dark) => isDark ? dark : light;

  switch (texture) {
    case ArticlePaperTexture.white:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.whiteStageLight,
          ArticlePaperPaletteColors.whiteStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.whitePaperLight,
          ArticlePaperPaletteColors.whitePaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.whitePaperBorderLight,
          ArticlePaperPaletteColors.whitePaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.whiteTextLight,
          ArticlePaperPaletteColors.whiteTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.whiteSecondaryTextLight,
          ArticlePaperPaletteColors.whiteSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.whiteAccentLight,
          ArticlePaperPaletteColors.whiteAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.whiteBadgeBackgroundLight,
          ArticlePaperPaletteColors.whiteBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.whiteBadgeTextLight,
          ArticlePaperPaletteColors.whiteBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.whiteOverlayLight,
          ArticlePaperPaletteColors.whiteOverlayDark,
        ),
      );
    case ArticlePaperTexture.cream:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.creamStageLight,
          ArticlePaperPaletteColors.creamStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.creamPaperLight,
          ArticlePaperPaletteColors.creamPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.creamPaperBorderLight,
          ArticlePaperPaletteColors.creamPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.creamTextLight,
          ArticlePaperPaletteColors.creamTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.creamSecondaryTextLight,
          ArticlePaperPaletteColors.creamSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.creamAccentLight,
          ArticlePaperPaletteColors.creamAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.creamBadgeBackgroundLight,
          ArticlePaperPaletteColors.creamBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.creamBadgeTextLight,
          ArticlePaperPaletteColors.creamBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: paper(
          ArticlePaperPaletteColors.creamOverlayLight,
          ArticlePaperPaletteColors.creamOverlayDark,
        ),
      );
    case ArticlePaperTexture.sepia:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.sepiaStageLight,
          ArticlePaperPaletteColors.sepiaStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.sepiaPaperLight,
          ArticlePaperPaletteColors.sepiaPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.sepiaPaperBorderLight,
          ArticlePaperPaletteColors.sepiaPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.sepiaTextLight,
          ArticlePaperPaletteColors.sepiaTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.sepiaSecondaryTextLight,
          ArticlePaperPaletteColors.sepiaSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.sepiaAccentLight,
          ArticlePaperPaletteColors.sepiaAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.sepiaBadgeBackgroundLight,
          ArticlePaperPaletteColors.sepiaBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.sepiaBadgeTextLight,
          ArticlePaperPaletteColors.sepiaBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.10),
        overlayColor: paper(
          ArticlePaperPaletteColors.sepiaOverlayLight,
          ArticlePaperPaletteColors.sepiaOverlayDark,
        ),
      );
    case ArticlePaperTexture.parchment:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.parchmentStageLight,
          ArticlePaperPaletteColors.parchmentStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.parchmentPaperLight,
          ArticlePaperPaletteColors.parchmentPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.parchmentPaperBorderLight,
          ArticlePaperPaletteColors.parchmentPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.parchmentTextLight,
          ArticlePaperPaletteColors.parchmentTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.parchmentSecondaryTextLight,
          ArticlePaperPaletteColors.parchmentSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.parchmentAccentLight,
          ArticlePaperPaletteColors.parchmentAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.parchmentBadgeBackgroundLight,
          ArticlePaperPaletteColors.parchmentBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.parchmentBadgeTextLight,
          ArticlePaperPaletteColors.parchmentBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.12),
        overlayColor: paper(
          ArticlePaperPaletteColors.parchmentOverlayLight,
          ArticlePaperPaletteColors.parchmentOverlayDark,
        ),
      );
    case ArticlePaperTexture.eyeCare:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.eyeCareStageLight,
          ArticlePaperPaletteColors.eyeCareStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.eyeCarePaperLight,
          ArticlePaperPaletteColors.eyeCarePaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.eyeCarePaperBorderLight,
          ArticlePaperPaletteColors.eyeCarePaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.eyeCareTextLight,
          ArticlePaperPaletteColors.eyeCareTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.eyeCareSecondaryTextLight,
          ArticlePaperPaletteColors.eyeCareSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.eyeCareAccentLight,
          ArticlePaperPaletteColors.eyeCareAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.eyeCareBadgeBackgroundLight,
          ArticlePaperPaletteColors.eyeCareBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.eyeCareBadgeTextLight,
          ArticlePaperPaletteColors.eyeCareBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.eyeCareOverlayLight,
          ArticlePaperPaletteColors.eyeCareOverlayDark,
        ),
      );
    case ArticlePaperTexture.quiet:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.quietStageLight,
          ArticlePaperPaletteColors.quietStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.quietPaperLight,
          ArticlePaperPaletteColors.quietPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.quietPaperBorderLight,
          ArticlePaperPaletteColors.quietPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.quietTextLight,
          ArticlePaperPaletteColors.quietTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.quietSecondaryTextLight,
          ArticlePaperPaletteColors.quietSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.quietAccentLight,
          ArticlePaperPaletteColors.quietAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.quietBadgeBackgroundLight,
          ArticlePaperPaletteColors.quietBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.quietBadgeTextLight,
          ArticlePaperPaletteColors.quietBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.quietOverlayLight,
          ArticlePaperPaletteColors.quietOverlayDark,
        ),
      );
    case ArticlePaperTexture.night:
      return ArticleTemplatePalette(
        stageBackground: ArticlePaperPaletteColors.nightStage,
        paperColor: ArticlePaperPaletteColors.nightPaper,
        paperBorderColor: ArticlePaperPaletteColors.nightPaperBorder,
        textColor: ArticlePaperPaletteColors.nightText,
        secondaryTextColor: ArticlePaperPaletteColors.nightSecondaryText,
        accentColor: ArticlePaperPaletteColors.nightAccent,
        badgeBackground: ArticlePaperPaletteColors.nightBadgeBackground,
        badgeTextColor: ArticlePaperPaletteColors.nightBadgeText,
        shadowColor: AppColors.black.withValues(alpha: 0.42),
        overlayColor: ArticlePaperPaletteColors.nightOverlay,
      );
  }
}

@immutable
class ArticleTypographySpec {
  const ArticleTypographySpec({
    required this.titleStyle,
    required this.bodyStyle,
    required this.captionStyle,
    required this.placeholderStyle,
    required this.badgeStyle,
  });

  final TextStyle titleStyle;
  final TextStyle bodyStyle;
  final TextStyle captionStyle;
  final TextStyle placeholderStyle;
  final TextStyle badgeStyle;
}

ArticleTypographySpec resolveArticleTypography(
  BuildContext context,
  ArticleTemplatePreset template,
  ArticleFontPreset fontPreset,
) {
  final palette = resolveArticleTemplatePalette(context, template);

  TextStyle base({
    required double size,
    FontWeight weight = FontWeight.normal,
    double height = 1.7,
    Color? color,
  }) {
    final fallback = switch (fontPreset) {
      ArticleFontPreset.classic => const <String>[
        'Times New Roman',
        'STSong',
        'Songti SC',
      ],
      ArticleFontPreset.handwritten => const <String>['Kaiti SC', 'STKaiti'],
      ArticleFontPreset.rounded => const <String>[
        'PingFang SC',
        'SF Pro Rounded',
      ],
      ArticleFontPreset.mono => const <String>['Menlo', 'Monaco'],
      ArticleFontPreset.clean => const <String>['PingFang SC'],
    };

    return TextStyle(
      color: color ?? palette.textColor,
      fontSize: size,
      fontWeight: weight,
      height: height,
      letterSpacing: fontPreset == ArticleFontPreset.mono ? 0.15 : 0.05,
      fontFamily: switch (fontPreset) {
        ArticleFontPreset.classic => 'Times New Roman',
        ArticleFontPreset.handwritten => 'Kaiti SC',
        ArticleFontPreset.rounded => 'SF Pro Rounded',
        ArticleFontPreset.mono => 'Menlo',
        ArticleFontPreset.clean => null,
      },
      fontFamilyFallback: fallback,
    );
  }

  return ArticleTypographySpec(
    titleStyle: base(
      size: AppTypography.xl,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightHeadline,
    ),
    bodyStyle: base(size: AppTypography.base, height: articleBodyLineHeight()),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: articleBodyLineHeight(),
      color: palette.secondaryTextColor.withValues(alpha: 0.72),
    ),
    badgeStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightCompact,
      color: palette.badgeTextColor,
    ),
  );
}

/// 基于纸张质感的排版规格（替代 resolveArticleTypography）。
ArticleTypographySpec resolveArticleTypographyForPaper(
  BuildContext context,
  ArticlePaperTexture texture,
  ArticleFontPreset fontPreset,
) {
  final palette = resolveArticlePaperPalette(context, texture);

  TextStyle base({
    required double size,
    FontWeight weight = FontWeight.normal,
    double height = 1.7,
    Color? color,
  }) {
    final fallback = switch (fontPreset) {
      ArticleFontPreset.classic => const <String>[
        'STSong',
        'Songti SC',
        'Noto Serif CJK SC',
      ],
      ArticleFontPreset.handwritten => const <String>['STKaiti', 'Kaiti SC'],
      ArticleFontPreset.rounded => const <String>[
        'PingFang SC',
        'SF Pro Rounded',
      ],
      ArticleFontPreset.mono => const <String>['Menlo', 'Monaco'],
      ArticleFontPreset.clean => const <String>['PingFang SC'],
    };

    return TextStyle(
      color: color ?? palette.textColor,
      fontSize: size,
      fontWeight: weight,
      height: height,
      letterSpacing: fontPreset == ArticleFontPreset.mono ? 0.15 : 0.05,
      fontFamily: switch (fontPreset) {
        ArticleFontPreset.classic => 'Songti SC',
        ArticleFontPreset.handwritten => 'Kaiti SC',
        ArticleFontPreset.rounded => 'SF Pro Rounded',
        ArticleFontPreset.mono => 'Menlo',
        ArticleFontPreset.clean => null,
      },
      fontFamilyFallback: fallback,
    );
  }

  return ArticleTypographySpec(
    titleStyle: base(
      size: AppTypography.xl,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightHeadline,
    ),
    bodyStyle: base(size: AppTypography.base, height: articleBodyLineHeight()),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: articleBodyLineHeight(),
      color: palette.secondaryTextColor.withValues(alpha: 0.72),
    ),
    badgeStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightCompact,
      color: palette.badgeTextColor,
    ),
  );
}

class _ArticleBackdrop extends StatelessWidget {
  const _ArticleBackdrop({required this.template, required this.palette});

  final ArticleTemplatePreset template;
  final ArticleTemplatePalette palette;

  @override
  Widget build(BuildContext context) {
    const journalTapePrimaryWidth = 74.0;
    const journalTapePrimaryHeight = 24.0;
    const journalTapeSecondaryWidth = 58.0;
    const journalTapeSecondaryHeight = 20.0;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: palette.stageBackground,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight + 6),
      ),
      child: Stack(
        children: <Widget>[
          if (template == ArticleTemplatePreset.gentle) ...<Widget>[
            Positioned(
              top: -20,
              left: -10,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.twenty,
                height: AppSpacing.storyHeight,
                color: palette.accentColor.withValues(alpha: 0.16),
              ),
            ),
            Positioned(
              bottom: 10,
              right: -14,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.buttonHeightSm,
                height: AppSpacing.storyHeight + AppSpacing.sm,
                color: ArticleTemplateColors.gentleBackdropMint.withValues(
                  alpha: 0.26,
                ),
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.ritual)
            Positioned.fill(
              child: CustomPaint(painter: _RitualBackdropPainter(palette)),
            ),
          if (template == ArticleTemplatePreset.diffuse) ...<Widget>[
            Positioned(
              top: -18,
              right: -18,
              child: _BackdropBlob(
                width:
                    AppSpacing.oneHundred + AppSpacing.forty + AppSpacing.ten,
                height: AppSpacing.oneHundred + AppSpacing.twenty,
                color: ArticleTemplateColors.diffuseBackdropLavender.withValues(
                  alpha: 0.3,
                ),
              ),
            ),
            Positioned(
              bottom: -12,
              left: -10,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.forty,
                height: AppSpacing.largeButtonSize * 2,
                color: ArticleTemplateColors.diffuseBackdropPink.withValues(
                  alpha: 0.26,
                ),
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.journal) ...<Widget>[
            Positioned.fill(
              child: CustomPaint(painter: _JournalBackdropPainter(palette)),
            ),
            Positioned(
              top: 18,
              left: 18,
              child: _JournalTapeDecoration(
                width: journalTapePrimaryWidth,
                height: journalTapePrimaryHeight,
                angle: -0.16,
                color: ArticleTemplateColors.journalTape.withValues(
                  alpha: 0.92,
                ),
              ),
            ),
            Positioned(
              top: 34,
              right: 24,
              child: _JournalTapeDecoration(
                width: journalTapeSecondaryWidth,
                height: journalTapeSecondaryHeight,
                angle: 0.2,
                color: ArticleTemplateColors.journalTape.withValues(alpha: 0.7),
              ),
            ),
            Positioned(
              bottom: 36,
              right: 18,
              child: const _JournalStickerDecoration(
                label: 'MEMO',
                angle: 0.12,
              ),
            ),
            Positioned(
              bottom: 56,
              left: 24,
              child: const _JournalStickerDecoration(
                label: 'TODAY',
                angle: -0.08,
                compact: true,
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.tech)
            Positioned.fill(
              child: CustomPaint(painter: _TechBackdropPainter(palette)),
            ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: palette.overlayColor,
                borderRadius: BorderRadius.circular(
                  AppSpacing.radiusTwentyEight + 6,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticlePageIndicator extends StatelessWidget {
  const _ArticlePageIndicator({required this.label, required this.palette});

  final String label;
  final ArticleTemplatePalette palette;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: palette.badgeBackground,
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            border: Border.all(
              color: palette.paperBorderColor.withValues(alpha: 0.6),
              width: AppSpacing.hairline,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            child: Text(
              label,
              style: TextStyle(
                color: palette.badgeTextColor,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ArticleBookChromePainter extends CustomPainter {
  const _ArticleBookChromePainter({
    required this.template,
    required this.palette,
    required this.pageIndex,
    required this.totalPages,
  });

  final ArticleTemplatePreset template;
  final ArticleTemplatePalette palette;
  final int pageIndex;
  final int totalPages;

  @override
  void paint(Canvas canvas, Size size) {
    final spineWidth = lerpDouble(
      18,
      26,
      math.min(totalPages / 12, 1).toDouble(),
    )!;
    final spineRect = Rect.fromLTWH(0, 0, spineWidth, size.height);
    final spinePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          AppColors.black.withValues(alpha: 0.18),
          palette.paperBorderColor.withValues(alpha: 0.16),
          AppColors.white.withValues(alpha: 0.08),
        ],
      ).createShader(spineRect);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        spineRect,
        const Radius.circular(AppSpacing.radiusTwentyEight),
      ),
      spinePaint,
    );

    final foreEdgeRect = Rect.fromLTWH(size.width - 18, 0, 18, size.height);
    final foreEdgePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          palette.paperBorderColor.withValues(alpha: 0.04),
          palette.paperBorderColor.withValues(alpha: 0.2),
          AppColors.white.withValues(alpha: 0.22),
        ],
      ).createShader(foreEdgeRect);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        foreEdgeRect,
        const Radius.circular(AppSpacing.radiusTwentyEight),
      ),
      foreEdgePaint,
    );

    switch (template) {
      case ArticleTemplatePreset.ritual:
        final embossPaint = Paint()
          ..color = palette.accentColor.withValues(alpha: 0.18)
          ..strokeWidth = 1.4;
        canvas.drawLine(
          Offset(spineWidth + 6, 18),
          Offset(spineWidth + 6, size.height - 18),
          embossPaint,
        );
        canvas.drawLine(
          Offset(spineWidth + 11, 18),
          Offset(spineWidth + 11, size.height - 18),
          embossPaint,
        );
        break;
      case ArticleTemplatePreset.diffuse:
        final hazePaint = Paint()
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18)
          ..color = palette.accentColor.withValues(alpha: 0.14);
        canvas.drawCircle(
          Offset(size.width * 0.86, size.height * 0.18),
          12,
          hazePaint,
        );
        canvas.drawCircle(
          Offset(size.width * 0.14, size.height * 0.82),
          14,
          hazePaint,
        );
        break;
      case ArticleTemplatePreset.journal:
        final holePaint = Paint()
          ..color = palette.paperBorderColor.withValues(alpha: 0.3);
        for (var index = 0; index < 6; index += 1) {
          final dy = 42.0 + (index * ((size.height - 84) / 5));
          canvas.drawCircle(Offset(spineWidth + 6, dy), 2.4, holePaint);
        }
        break;
      case ArticleTemplatePreset.tech:
        final techPaint = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2
          ..color = palette.accentColor.withValues(alpha: 0.42);
        final path = Path()
          ..moveTo(size.width - 28, 22)
          ..lineTo(size.width - 16, 22)
          ..lineTo(size.width - 16, 42)
          ..lineTo(size.width - 8, 42)
          ..moveTo(size.width - 30, size.height - 22)
          ..lineTo(size.width - 18, size.height - 22)
          ..lineTo(size.width - 18, size.height - 42)
          ..lineTo(size.width - 10, size.height - 42);
        canvas.drawPath(path, techPaint);
        break;
      case ArticleTemplatePreset.gentle:
        final ribbonPaint = Paint()
          ..color = palette.accentColor.withValues(alpha: 0.14)
          ..strokeWidth = 2.2
          ..strokeCap = StrokeCap.round;
        final ribbonInset = 16 + (pageIndex % 2) * 2;
        canvas.drawLine(
          Offset(spineWidth + ribbonInset, 24),
          Offset(spineWidth + ribbonInset, size.height - 24),
          ribbonPaint,
        );
        break;
    }
  }

  @override
  bool shouldRepaint(covariant _ArticleBookChromePainter oldDelegate) {
    return oldDelegate.template != template ||
        oldDelegate.palette != palette ||
        oldDelegate.pageIndex != pageIndex ||
        oldDelegate.totalPages != totalPages;
  }
}

class _ArticlePolygonClipper extends CustomClipper<Path> {
  const _ArticlePolygonClipper(this.points);

  final List<Offset> points;

  @override
  Path getClip(Size size) {
    final path = Path();
    if (points.isEmpty) {
      return path;
    }
    path.moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }

  @override
  bool shouldReclip(covariant _ArticlePolygonClipper oldClipper) {
    if (identical(points, oldClipper.points)) {
      return false;
    }
    if (points.length != oldClipper.points.length) {
      return true;
    }
    for (var index = 0; index < points.length; index += 1) {
      if (points[index] != oldClipper.points[index]) {
        return true;
      }
    }
    return false;
  }
}

/// 后翻降级路径用的水平裁剪器：从左边缘向右展开 [revealWidth] 宽度。
/// 后翻降级路径的圆筒卷曲模拟。
///
/// 将 [child]（翻页内容）切成 [_sliceCount] 条垂直切片，
/// 每条切片根据它在 [ReverseFlipPose] 圆筒模型中的位置做：
/// - 水平压缩（透视缩放）：圆筒背面的切片更窄
/// - 水平偏移：模拟圆筒的 sin(θ) 投影
/// - 明暗变化：圆筒背面更暗
///
/// 效果：页面先以卷曲圆筒形态从左边缘出现，然后逐渐展开铺平。
/// 独立于父级动画 tick 的纹理截图层。
///
/// 父级 [ArticleReadOnlyBookDeck] 每帧 `setState` 驱动翻页动画，
/// 如果截图层在同一个 build 树里，[RepaintBoundary] 会被反复标脏，
/// `debugNeedsPaint` 永远为 true，`toImage()` 永远失败。
///
/// 这个 widget 用 [didUpdateWidget] + `listEquals` 判断 [capturePages]
/// 是否真的变了，只在变化时才 rebuild 子树，让 [RepaintBoundary] 有机会
/// 完成 paint 并被截图。
class _StableTextureCaptureLayer extends StatefulWidget {
  const _StableTextureCaptureLayer({
    super.key,
    required this.capturePages,
    required this.pageSize,
    required this.boundaryKeys,
    required this.buildPage,
  });

  final List<int> capturePages;
  final Size pageSize;
  final Map<int, GlobalKey> boundaryKeys;
  final Widget Function(int index) buildPage;

  @override
  State<_StableTextureCaptureLayer> createState() =>
      _StableTextureCaptureLayerState();
}

class _StableTextureCaptureLayerState
    extends State<_StableTextureCaptureLayer> {
  late List<int> _capturePages;
  late Map<int, Widget> _cachedWidgets;

  @override
  void initState() {
    super.initState();
    _capturePages = List<int>.of(widget.capturePages);
    _rebuildCache();
  }

  @override
  void didUpdateWidget(covariant _StableTextureCaptureLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.capturePages, _capturePages) ||
        widget.pageSize != oldWidget.pageSize) {
      _capturePages = List<int>.of(widget.capturePages);
      _rebuildCache();
    }
    // 不调用 setState —— 只有 capturePages 真正变化时才重建。
    // _cachedWidgets 保证 RepaintBoundary 子树在动画 tick 期间不被重建，
    // 让 debugNeedsPaint 有机会变为 false，纹理截图才能成功。
  }

  void _rebuildCache() {
    _cachedWidgets = {
      for (final index in _capturePages) index: widget.buildPage(index),
    };
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ExcludeSemantics(
        child: Opacity(
          opacity: 0.001,
          child: Align(
            alignment: Alignment.topLeft,
            child: OverflowBox(
              alignment: Alignment.topLeft,
              minWidth: widget.pageSize.width,
              maxWidth: widget.pageSize.width,
              minHeight: widget.pageSize.height,
              maxHeight: widget.pageSize.height * _capturePages.length,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: _capturePages
                    .map((index) {
                      return RepaintBoundary(
                        key: widget.boundaryKeys[index],
                        child: SizedBox(
                          width: widget.pageSize.width,
                          height: widget.pageSize.height,
                          child: _cachedWidgets[index] ??
                              const SizedBox.shrink(),
                        ),
                      );
                    })
                    .toList(growable: false),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ArticleReaderStagePainter extends CustomPainter {
  const _ArticleReaderStagePainter({
    required this.palette,
    required this.pageRect,
    required this.pageCount,
    this.activeCorner,
    this.progress = 0,
  });

  final ArticleTemplatePalette palette;
  final Rect pageRect;
  final int pageCount;
  final _ArticlePageCurlCorner? activeCorner;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final stageRect = Offset.zero & size;
    final softenedDeskBase = Color.lerp(
      palette.paperColor,
      AppColors.worksBackground,
      0.82,
    )!;
    final deskTop = Color.alphaBlend(
      palette.stageBackground.withValues(alpha: 0.64),
      softenedDeskBase,
    );
    final deskBottom = Color.alphaBlend(
      palette.stageBackground.withValues(alpha: 0.58),
      Color.lerp(softenedDeskBase, AppColors.worksDrawerBg, 0.28)!,
    );
    final stagePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: <Color>[
          deskTop,
          Color.alphaBlend(
            palette.stageBackground.withValues(alpha: 0.5),
            AppColors.iosSystemSurfaceDark,
          ),
          deskBottom,
        ],
        stops: const <double>[0.0, 0.52, 1.0],
      ).createShader(stageRect);
    canvas.drawRect(stageRect, stagePaint);

    final haloPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(0, -0.18),
        radius: 0.92,
        colors: <Color>[
          AppColors.white.withValues(alpha: 0.05),
          palette.paperColor.withValues(alpha: 0.03),
          AppColors.transparent,
        ],
      ).createShader(stageRect);
    canvas.drawRect(stageRect, haloPaint);

    final stageSpec = resolveArticleReaderStageSpec();
    final spineRect = Rect.fromCenter(
      center: Offset(pageRect.center.dx, pageRect.center.dy),
      width: stageSpec.spineShadowWidth,
      height: pageRect.height + 32,
    );
    final spinePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          AppColors.black.withValues(alpha: 0.03),
          AppColors.black.withValues(alpha: 0.18 + progress * 0.08),
          AppColors.iosProfileSurfaceLight.withValues(alpha: 0.06),
          AppColors.transparent,
        ],
        stops: const <double>[0.0, 0.36, 0.72, 1.0],
      ).createShader(spineRect);
    canvas.drawRect(spineRect, spinePaint);

    final stackPaint = Paint()
      ..color = AppColors.iosProfileSurfaceLight.withValues(alpha: 0.14)
      ..strokeWidth = 1;
    final stackCount = math.min(pageCount, stageSpec.pageStackCount);
    for (var index = 0; index < stackCount; index += 1) {
      final inset = (index + 1) * stageSpec.pageStackSpacing;
      final alpha = 0.16 - (index * 0.022);
      stackPaint.color = AppColors.iosProfileSurfaceLight.withValues(
        alpha: alpha.clamp(0.04, 0.16).toDouble(),
      );
      final leftX = pageRect.left - inset;
      final rightX = pageRect.right + inset;
      canvas.drawLine(
        Offset(leftX, pageRect.top + 12),
        Offset(leftX, pageRect.bottom - 12),
        stackPaint,
      );
      canvas.drawLine(
        Offset(rightX, pageRect.top + 12),
        Offset(rightX, pageRect.bottom - 12),
        stackPaint,
      );
    }

    if (activeCorner != null && progress > 0) {
      final isForward =
          activeCorner == _ArticlePageCurlCorner.topRight ||
          activeCorner == _ArticlePageCurlCorner.bottomRight;
      final foldShadowRect = Rect.fromLTWH(
        isForward ? pageRect.right - (pageRect.width * 0.32) : pageRect.left,
        pageRect.top,
        pageRect.width * 0.32,
        pageRect.height,
      );
      final foldShadowPaint = Paint()
        ..shader = LinearGradient(
          begin: isForward ? Alignment.centerRight : Alignment.centerLeft,
          end: isForward ? Alignment.centerLeft : Alignment.centerRight,
          colors: <Color>[
            AppColors.black.withValues(alpha: 0.14 * progress),
            AppColors.black.withValues(alpha: 0.04 * progress),
            AppColors.iosProfileSurfaceLight.withValues(alpha: 0.02 * progress),
            AppColors.transparent,
          ],
        ).createShader(foldShadowRect);
      canvas.drawRect(foldShadowRect, foldShadowPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _ArticleReaderStagePainter oldDelegate) {
    return oldDelegate.palette != palette ||
        oldDelegate.pageRect != pageRect ||
        oldDelegate.pageCount != pageCount ||
        oldDelegate.activeCorner != activeCorner ||
        oldDelegate.progress != progress;
  }
}

class _ArticleBookStylePagerHintPainter extends CustomPainter {
  const _ArticleBookStylePagerHintPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    const foldSize = 24.0;
    final foldPaint = Paint()
      ..shader =
          LinearGradient(
            begin: Alignment.topRight,
            end: Alignment.bottomLeft,
            colors: <Color>[
              AppColors.white.withValues(alpha: 0.42),
              palette.paperBorderColor.withValues(alpha: 0.28),
            ],
          ).createShader(
            Rect.fromLTWH(size.width - foldSize, 0, foldSize, foldSize),
          );
    final topFold = Path()
      ..moveTo(size.width, 0)
      ..lineTo(size.width - foldSize, 0)
      ..lineTo(size.width, foldSize)
      ..close();
    final bottomFold = Path()
      ..moveTo(size.width, size.height)
      ..lineTo(size.width - foldSize, size.height)
      ..lineTo(size.width, size.height - foldSize)
      ..close();
    canvas.drawPath(topFold, foldPaint);
    canvas.drawPath(bottomFold, foldPaint);
  }

  @override
  bool shouldRepaint(covariant _ArticleBookStylePagerHintPainter oldDelegate) {
    return oldDelegate.palette != palette;
  }
}

class _ArticleSemanticBlock extends StatelessWidget {
  const _ArticleSemanticBlock({required this.block, required this.typography});

  final ArticleDocumentBlock block;
  final ArticleTypographySpec typography;

  @override
  Widget build(BuildContext context) {
    final titleFont = typography.titleStyle.fontSize ?? AppTypography.xl;
    final bodyFont = typography.bodyStyle.fontSize ?? AppTypography.base;
    final style = switch (block.type) {
      ArticleDocumentBlockType.heading2 => typography.titleStyle.copyWith(
        fontSize: titleFont * 0.82,
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.heading3 => typography.bodyStyle.copyWith(
        fontSize: math.max(bodyFont * 1.14, 18),
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.sectionTitle => typography.titleStyle.copyWith(
        fontSize: math.max(bodyFont * 1.28, 20),
        fontWeight: AppTypography.bold,
        letterSpacing: 0.18,
      ),
      _ => typography.bodyStyle,
    };
    return Text(block.text.trim(), style: style);
  }
}

class _ArticlePageImage extends StatelessWidget {
  const _ArticlePageImage({
    required this.imageUrl,
    required this.borderRadius,
    required this.aspectRatio,
  });

  final String imageUrl;
  final double borderRadius;
  final double aspectRatio;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: AspectRatio(
        aspectRatio: aspectRatio,
        child: ArticleAdaptiveImage(imageUrl: imageUrl),
      ),
    );
  }
}

class _TemplatePreviewFiller extends StatelessWidget {
  const _TemplatePreviewFiller({
    required this.template,
    required this.fontPreset,
    required this.label,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String label;

  @override
  Widget build(BuildContext context) {
    final typography = resolveArticleTypography(context, template, fontPreset);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: AppSpacing.buttonHeightXs,
          height: AppSpacing.six,
          decoration: BoxDecoration(
            color: typography.captionStyle.color?.withValues(alpha: 0.35),
            borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: typography.captionStyle,
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Expanded(
          child: Text(
            '春风起，纸面轻轻落下',
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: typography.bodyStyle.copyWith(
              fontSize: AppTypography.xsPlus,
            ),
          ),
        ),
      ],
    );
  }
}

class _BackdropBlob extends StatelessWidget {
  const _BackdropBlob({
    required this.width,
    required this.height,
    required this.color,
  });

  final double width;
  final double height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: 0.18,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(height / 2),
        ),
      ),
    );
  }
}

class _JournalTapeDecoration extends StatelessWidget {
  const _JournalTapeDecoration({
    required this.width,
    required this.height,
    required this.angle,
    required this.color,
  });

  final double width;
  final double height;
  final double angle;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: angle,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(height / 2),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: AppColors.black.withValues(alpha: 0.06),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
      ),
    );
  }
}

class _JournalStickerDecoration extends StatelessWidget {
  const _JournalStickerDecoration({
    required this.label,
    required this.angle,
    this.compact = false,
  });

  final String label;
  final double angle;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final background = compact
        ? ArticleTemplateColors.journalSticker.withValues(alpha: 0.9)
        : ArticleTemplateColors.journalSticker.withValues(alpha: 0.82);
    return Transform.rotate(
      angle: angle,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? 10 : 12,
          vertical: compact ? 5 : 6,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.44),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: AppColors.black.withValues(alpha: 0.08),
              blurRadius: 14,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Text(
          label,
          style: TextStyle(
            color: ArticleTemplateColors.journalTextLight.withValues(
              alpha: 0.9,
            ),
            fontSize: compact ? AppTypography.xs : AppTypography.xsPlus,
            fontWeight: AppTypography.semiBold,
            letterSpacing: 0.8,
          ),
        ),
      ),
    );
  }
}

class _JournalPaperClipper extends CustomClipper<Path> {
  const _JournalPaperClipper();

  @override
  Path getClip(Size size) {
    return Path()
      ..moveTo(size.width * 0.02, size.height * 0.02)
      ..quadraticBezierTo(
        size.width * 0.16,
        -2,
        size.width * 0.3,
        size.height * 0.03,
      )
      ..quadraticBezierTo(
        size.width * 0.5,
        size.height * 0.01,
        size.width * 0.72,
        size.height * 0.04,
      )
      ..quadraticBezierTo(
        size.width * 0.9,
        size.height * 0.02,
        size.width * 0.98,
        size.height * 0.05,
      )
      ..lineTo(size.width * 0.97, size.height * 0.88)
      ..quadraticBezierTo(
        size.width * 0.85,
        size.height * 0.93,
        size.width * 0.76,
        size.height * 0.9,
      )
      ..quadraticBezierTo(
        size.width * 0.58,
        size.height * 0.95,
        size.width * 0.42,
        size.height * 0.91,
      )
      ..quadraticBezierTo(
        size.width * 0.25,
        size.height * 0.95,
        size.width * 0.08,
        size.height * 0.9,
      )
      ..quadraticBezierTo(
        -4,
        size.height * 0.78,
        size.width * 0.02,
        size.height * 0.62,
      )
      ..close();
  }

  @override
  bool shouldReclip(covariant CustomClipper<Path> oldClipper) => false;
}

class _JournalPaperTexturePainter extends CustomPainter {
  const _JournalPaperTexturePainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final fiberPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.07)
      ..strokeWidth = 0.8
      ..strokeCap = StrokeCap.round;
    for (var index = 0; index < 36; index += 1) {
      final y = 14.0 + (index * (size.height / 36));
      final startX = 8.0 + ((index % 5) * 6);
      final endX = size.width - 12 - ((index % 4) * 4);
      canvas.drawLine(Offset(startX, y), Offset(endX, y + 1.6), fiberPaint);
    }

    final grainPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.05)
      ..style = PaintingStyle.fill;
    for (var index = 0; index < 42; index += 1) {
      final dx = 10 + ((index * 23) % (size.width - 20).clamp(1, 99999));
      final dy = 18 + ((index * 31) % (size.height - 36).clamp(1, 99999));
      canvas.drawCircle(Offset(dx.toDouble(), dy.toDouble()), 0.9, grainPaint);
    }

    final marginPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.2)
      ..strokeWidth = 1.2;
    canvas.drawLine(
      Offset(size.width * 0.16, 0),
      Offset(size.width * 0.16, size.height),
      marginPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _JournalPaperTexturePainter oldDelegate) {
    return oldDelegate.palette != palette;
  }
}

class _JournalBackdropPainter extends CustomPainter {
  const _JournalBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.32)
      ..strokeWidth = 1;
    for (var y = 22.0; y < size.height; y += 20) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), linePaint);
    }

    final marginPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.18)
      ..strokeWidth = 1.4;
    canvas.drawLine(
      Offset(size.width * 0.18, 0),
      Offset(size.width * 0.18, size.height),
      marginPaint,
    );

    final blotPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.08)
      ..style = PaintingStyle.fill;
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.72, size.height * 0.2),
        width: size.width * 0.26,
        height: size.height * 0.14,
      ),
      blotPaint,
    );
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.32, size.height * 0.74),
        width: size.width * 0.22,
        height: size.height * 0.12,
      ),
      blotPaint,
    );

    final tapePaint = Paint()..color = ArticleTemplateColors.journalTape;
    canvas.save();
    canvas.translate(18, 18);
    canvas.rotate(-0.18);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(0, 0, 68, 26),
        const Radius.circular(10),
      ),
      tapePaint,
    );
    canvas.restore();

    final stickerPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = ArticleTemplateColors.journalSticker;
    canvas.drawArc(
      Rect.fromCircle(
        center: Offset(size.width - 34, size.height - 32),
        radius: 18,
      ),
      -0.6,
      2.8,
      false,
      stickerPaint,
    );

    final doodlePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round
      ..color = palette.textColor.withValues(alpha: 0.16);
    final path = Path()
      ..moveTo(size.width * 0.7, size.height * 0.8)
      ..quadraticBezierTo(
        size.width * 0.77,
        size.height * 0.76,
        size.width * 0.84,
        size.height * 0.82,
      )
      ..quadraticBezierTo(
        size.width * 0.9,
        size.height * 0.86,
        size.width * 0.93,
        size.height * 0.8,
      );
    canvas.drawPath(path, doodlePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _RitualBackdropPainter extends CustomPainter {
  const _RitualBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final borderPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.48)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(14, 14, size.width - 28, size.height - 28),
      const Radius.circular(24),
    );
    canvas.drawRRect(rect, borderPaint);

    final accentPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.22)
      ..strokeWidth = 2;
    canvas.drawLine(
      const Offset(28, 34),
      Offset(size.width - 28, 34),
      accentPaint,
    );
    canvas.drawLine(
      Offset(28, size.height - 34),
      Offset(size.width - 28, size.height - 34),
      accentPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _TechBackdropPainter extends CustomPainter {
  const _TechBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.12)
      ..strokeWidth = 1;
    for (var x = 0.0; x < size.width; x += 20) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (var y = 0.0; y < size.height; y += 20) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    final glowPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.26)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 24);
    canvas.drawCircle(
      Offset(size.width * 0.82, size.height * 0.14),
      24,
      glowPaint,
    );
    canvas.drawCircle(
      Offset(size.width * 0.18, size.height * 0.86),
      28,
      glowPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
