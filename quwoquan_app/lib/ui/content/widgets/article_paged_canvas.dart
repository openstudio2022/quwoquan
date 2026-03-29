import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_pagination_engine.dart';
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
}) {
  final hasLegacyStructuredPages = fallbackPages
      .skip(1)
      .any((page) => page.title.trim().isNotEmpty);
  if (hasLegacyStructuredPages) {
    return fallbackPages;
  }
  final stageWidth = constraints.maxWidth.isFinite
      ? constraints.maxWidth
      : MediaQuery.sizeOf(context).width;
  final metrics = resolveArticleCanvasMetrics(
    context,
    constraints,
    variant: variant,
  );
  final typography = resolveArticleTypography(context, template, fontPreset);
  return ArticlePaginationEngine.paginate(
    document: document,
    metrics: metrics,
    stageWidth: stageWidth,
    titleStyle: typography.titleStyle,
    bodyStyle: typography.bodyStyle,
  );
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
    this.contentPadding,
    this.showIndicator = true,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final int pageIndex;
  final int totalPages;
  final Widget child;
  final double aspectRatio;
  final EdgeInsets? contentPadding;
  final bool showIndicator;

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(context, template);

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
      child: Padding(
        padding:
            contentPadding ??
            EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerLg,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
            ),
        child: child,
      ),
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
              padding: EdgeInsets.all(AppSpacing.containerSm),
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
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              child: paper,
            ),
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
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;

  @override
  Widget build(BuildContext context) {
    final typography = resolveArticleTypography(context, template, fontPreset);

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (page.title.trim().isNotEmpty) ...<Widget>[
            Text(page.title.trim(), style: typography.titleStyle),
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          if (page.contentBlocks.isNotEmpty)
            ...page.contentBlocks.map(
              (block) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
                child: _ArticleSemanticBlock(
                  block: block,
                  typography: typography,
                ),
              ),
            ),
          if (page.imageUrl.trim().isNotEmpty &&
              !page.usesWrappedLayout) ...<Widget>[
            _ArticlePageImage(
              imageUrl: page.imageUrl.trim(),
              borderRadius: AppSpacing.radiusTwenty,
              aspectRatio: template == ArticleTemplatePreset.journal
                  ? 1
                  : 4 / 3,
            ),
            if (page.caption.trim().isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(page.caption.trim(), style: typography.captionStyle),
            ],
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          if (page.imageUrl.trim().isNotEmpty && page.usesWrappedLayout)
            _ArticleWrappedTextImage(
              body: page.body.trim(),
              imageUrl: page.imageUrl.trim(),
              imageLayout: page.imageLayout,
              typography: typography,
            )
          else if (page.body.trim().isNotEmpty)
            Text(page.body.trim(), style: typography.bodyStyle),
        ],
      ),
    );
  }
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
    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            child: AspectRatio(
              aspectRatio: template == ArticleTemplatePreset.journal
                  ? 4 / 5
                  : 4 / 3,
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
          ),
          SizedBox(height: AppSpacing.containerMd),
          if (frontispieceBody.isNotEmpty)
            Text(frontispieceBody, style: typography.bodyStyle),
        ],
      ),
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
  late final PageController _pageController;
  late final AnimationController _curlController;
  _ArticlePageCurlCorner? _activeCurlCorner;
  Offset? _dragOrigin;
  double _curlProgress = 0;
  bool _overflowLocked = false;
  late int _currentPage;
  DateTime? _pageTransitionStartedAt;
  String? _pageTransitionMechanism;
  ArticleReaderFallbackReason? _reportedFallbackReason;

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
    _curlController =
        AnimationController(
          vsync: this,
          duration: const Duration(milliseconds: 260),
          lowerBound: 0,
          upperBound: 1,
        )..addListener(() {
          if (!mounted) {
            return;
          }
          setState(() {
            _curlProgress = _curlController.value;
          });
        });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onPageChanged?.call(_currentPage);
    });
    _maybeReportFallbackReason();
  }

  @override
  void didUpdateWidget(covariant ArticleReadOnlyBookDeck oldWidget) {
    super.didUpdateWidget(oldWidget);
    _maybeReportFallbackReason();
    final nextInitialPage = _safeInitialPage;
    if (widget.initialPage != oldWidget.initialPage &&
        _pageController.hasClients &&
        nextInitialPage != _currentPage) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_pageController.hasClients) {
          return;
        }
        _pageController.jumpToPage(nextInitialPage);
        setState(() {
          _currentPage = nextInitialPage;
        });
      });
    } else if (_currentPage >= widget.pages.length && widget.pages.isNotEmpty) {
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
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    _curlController.dispose();
    super.dispose();
  }

  bool _isForwardCorner(_ArticlePageCurlCorner corner) {
    return corner == _ArticlePageCurlCorner.topRight ||
        corner == _ArticlePageCurlCorner.bottomRight;
  }

  String _cornerName(_ArticlePageCurlCorner corner) {
    return switch (corner) {
      _ArticlePageCurlCorner.topLeft => 'top_left',
      _ArticlePageCurlCorner.topRight => 'top_right',
      _ArticlePageCurlCorner.bottomLeft => 'bottom_left',
      _ArticlePageCurlCorner.bottomRight => 'bottom_right',
    };
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

  void _emitPageCurlAbort(_ArticlePageCurlCorner corner) {
    final progress = _curlProgress;
    _clearPageTransition();
    if (progress <= 0) {
      return;
    }
    widget.onPageCurlAborted?.call(
      ArticleReaderPageCurlAbort(
        corner: _cornerName(corner),
        progress: progress,
      ),
    );
  }

  bool _canFlip(_ArticlePageCurlCorner corner) {
    if (widget.pages.length <= 1) {
      return false;
    }
    if (_isForwardCorner(corner)) {
      return _currentPage < widget.pages.length - 1;
    }
    return _currentPage > 0;
  }

  void _beginCurl(_ArticlePageCurlCorner corner, DragStartDetails details) {
    if (!_showsPageCurl || !_canFlip(corner)) {
      _activeCurlCorner = null;
      _dragOrigin = null;
      return;
    }
    _startPageTransition('page_curl');
    _dragOrigin = details.globalPosition;
    setState(() {
      _activeCurlCorner = corner;
    });
    _curlController.value = 0;
  }

  void _updateCurl(DragUpdateDetails details) {
    final corner = _activeCurlCorner;
    final dragOrigin = _dragOrigin;
    if (corner == null || dragOrigin == null) {
      return;
    }
    final delta = details.globalPosition - dragOrigin;
    final primaryDistance = _isForwardCorner(corner)
        ? (-delta.dx + delta.dy.abs() * 0.12)
        : (delta.dx + delta.dy.abs() * 0.12);
    _curlController.value = (primaryDistance / 180).clamp(0.0, 1.0);
  }

  Future<void> _endCurl(DragEndDetails details) async {
    final corner = _activeCurlCorner;
    if (corner == null) {
      return;
    }
    final velocityX = details.velocity.pixelsPerSecond.dx;
    final shouldCommit =
        _curlProgress > 0.38 ||
        (_isForwardCorner(corner) ? velocityX < -620 : velocityX > 620);
    if (!_canFlip(corner)) {
      _clearPageTransition();
      _resetCurl();
      if (_isForwardCorner(corner)) {
        widget.onOverflowNext?.call();
      } else {
        widget.onOverflowPrevious?.call();
      }
      return;
    }
    if (!shouldCommit) {
      _emitPageCurlAbort(corner);
      await _curlController.animateBack(
        0,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
      );
      _resetCurl();
      return;
    }
    await _curlController.animateTo(
      1,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
    if (!mounted) {
      return;
    }
    if (_isForwardCorner(corner)) {
      await _pageController.nextPage(
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOutCubic,
      );
    } else {
      await _pageController.previousPage(
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOutCubic,
      );
    }
    if (!mounted) {
      return;
    }
    _resetCurl();
  }

  void _resetCurl() {
    _dragOrigin = null;
    _curlController.value = 0;
    setState(() {
      _activeCurlCorner = null;
    });
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
      if (_activeCurlCorner == null) {
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

  @override
  Widget build(BuildContext context) {
    const pageCurlHotzoneExtent = 76.0;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        NotificationListener<ScrollNotification>(
          onNotification: _handleScrollNotification,
          child: PageView.builder(
            key: _useDegradedPager ? TestKeys.articleBookStylePager : null,
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
              final page = widget.pages[index];
              return Padding(
                padding: widget.pagePadding,
                child: ArticlePageShell(
                  template: widget.template,
                  fontPreset: widget.fontPreset,
                  pageIndex: index,
                  totalPages: widget.pages.length,
                  aspectRatio: widget.metrics.aspectRatio,
                  contentPadding: widget.metrics.contentPadding,
                  showIndicator: false,
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
                        ),
                ),
              );
            },
          ),
        ),
        if (_useDegradedPager)
          Positioned.fill(
            child: IgnorePointer(
              child: CustomPaint(
                painter: _ArticleBookStylePagerHintPainter(
                  resolveArticleTemplatePalette(context, widget.template),
                ),
              ),
            ),
          ),
        if (_showsPageCurl)
          Positioned.fill(
            key: TestKeys.articlePageCurlLayer,
            child: Stack(
              children: <Widget>[
                for (final corner in _ArticlePageCurlCorner.values)
                  Positioned(
                    top:
                        corner == _ArticlePageCurlCorner.topLeft ||
                            corner == _ArticlePageCurlCorner.topRight
                        ? 0
                        : null,
                    bottom:
                        corner == _ArticlePageCurlCorner.bottomLeft ||
                            corner == _ArticlePageCurlCorner.bottomRight
                        ? 0
                        : null,
                    left:
                        corner == _ArticlePageCurlCorner.topLeft ||
                            corner == _ArticlePageCurlCorner.bottomLeft
                        ? 0
                        : null,
                    right:
                        corner == _ArticlePageCurlCorner.topRight ||
                            corner == _ArticlePageCurlCorner.bottomRight
                        ? 0
                        : null,
                    width: pageCurlHotzoneExtent,
                    height: pageCurlHotzoneExtent,
                    child: GestureDetector(
                      key: _hotzoneKey(corner),
                      behavior: HitTestBehavior.opaque,
                      onPanStart: (details) => _beginCurl(corner, details),
                      onPanUpdate: _updateCurl,
                      onPanEnd: _endCurl,
                      onPanCancel: () {
                        final activeCorner = _activeCurlCorner;
                        if (activeCorner != null) {
                          _emitPageCurlAbort(activeCorner);
                        }
                        _resetCurl();
                      },
                    ),
                  ),
                if (_activeCurlCorner != null && _curlProgress > 0)
                  Positioned.fill(
                    child: IgnorePointer(
                      child: CustomPaint(
                        painter: _ArticlePageCurlPainter(
                          palette: resolveArticleTemplatePalette(
                            context,
                            widget.template,
                          ),
                          corner: _activeCurlCorner!,
                          progress: _curlProgress,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

enum _ArticlePageCurlCorner { topLeft, topRight, bottomLeft, bottomRight }

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
              showIndicator: false,
              contentPadding: const EdgeInsets.fromLTRB(8, 10, 8, 8),
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
    bodyStyle: base(
      size: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
    ),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
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

class _ArticlePageCurlPainter extends CustomPainter {
  const _ArticlePageCurlPainter({
    required this.palette,
    required this.corner,
    required this.progress,
  });

  final ArticleTemplatePalette palette;
  final _ArticlePageCurlCorner corner;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final isRight =
        corner == _ArticlePageCurlCorner.topRight ||
        corner == _ArticlePageCurlCorner.bottomRight;
    final isBottom =
        corner == _ArticlePageCurlCorner.bottomLeft ||
        corner == _ArticlePageCurlCorner.bottomRight;
    final foldWidth = lerpDouble(
      22,
      size.width * 0.5,
      progress.clamp(0.0, 1.0),
    )!;
    final foldHeight = lerpDouble(
      22,
      size.height * 0.44,
      progress.clamp(0.0, 1.0),
    )!;
    final cornerX = isRight ? size.width : 0.0;
    final cornerY = isBottom ? size.height : 0.0;
    final foldRect = Rect.fromLTWH(
      isRight ? size.width - foldWidth : 0,
      isBottom ? size.height - foldHeight : 0,
      foldWidth,
      foldHeight,
    );

    final shadowPath = Path()
      ..moveTo(cornerX, cornerY)
      ..lineTo(
        isRight ? size.width - foldWidth * 0.9 : foldWidth * 0.9,
        cornerY,
      )
      ..lineTo(
        cornerX,
        isBottom ? size.height - foldHeight * 0.9 : foldHeight * 0.9,
      )
      ..close();
    final shadowPaint = Paint()
      ..shader = RadialGradient(
        center: Alignment(isRight ? 1 : -1, isBottom ? 1 : -1),
        radius: 0.9,
        colors: <Color>[
          AppColors.black.withValues(alpha: 0.22 * progress),
          AppColors.black.withValues(alpha: 0.05 * progress),
          AppColors.transparent,
        ],
      ).createShader(foldRect.inflate(48));
    canvas.drawPath(shadowPath, shadowPaint);

    final foldPath = Path()
      ..moveTo(cornerX, cornerY)
      ..lineTo(isRight ? size.width - foldWidth : foldWidth, cornerY)
      ..lineTo(cornerX, isBottom ? size.height - foldHeight : foldHeight)
      ..close();
    final foldPaint = Paint()
      ..shader = LinearGradient(
        begin: isRight
            ? (isBottom ? Alignment.bottomRight : Alignment.topRight)
            : (isBottom ? Alignment.bottomLeft : Alignment.topLeft),
        end: isRight
            ? (isBottom ? Alignment.topLeft : Alignment.bottomLeft)
            : (isBottom ? Alignment.topRight : Alignment.bottomRight),
        colors: <Color>[
          AppColors.white.withValues(alpha: 0.86),
          palette.paperColor.withValues(alpha: 0.98),
          palette.paperBorderColor.withValues(alpha: 0.72),
        ],
      ).createShader(foldRect);
    canvas.drawPath(foldPath, foldPaint);

    final creasePaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.54)
      ..strokeWidth = 1.1
      ..style = PaintingStyle.stroke;
    canvas.drawLine(
      Offset(isRight ? size.width - foldWidth : foldWidth, cornerY),
      Offset(cornerX, isBottom ? size.height - foldHeight : foldHeight),
      creasePaint,
    );
  }

  @override
  bool shouldRepaint(covariant _ArticlePageCurlPainter oldDelegate) {
    return oldDelegate.palette != palette ||
        oldDelegate.corner != corner ||
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

class _ArticleWrappedTextImage extends StatelessWidget {
  const _ArticleWrappedTextImage({
    required this.body,
    required this.imageUrl,
    required this.imageLayout,
    required this.typography,
  });

  final String body;
  final String imageUrl;
  final String imageLayout;
  final ArticleTypographySpec typography;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final imageWidth = math.min(132.0, constraints.maxWidth * 0.42);
        final image = SizedBox(
          width: imageWidth,
          child: _ArticlePageImage(
            imageUrl: imageUrl,
            borderRadius: AppSpacing.radiusTwenty,
            aspectRatio: 1,
          ),
        );
        final text = Expanded(child: Text(body, style: typography.bodyStyle));
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: imageLayout == 'wrapRight'
              ? <Widget>[text, SizedBox(width: AppSpacing.containerSm), image]
              : <Widget>[image, SizedBox(width: AppSpacing.containerSm), text],
        );
      },
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
