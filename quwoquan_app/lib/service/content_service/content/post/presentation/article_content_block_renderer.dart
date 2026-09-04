import 'dart:async';

import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/immersive_media_wait_motion.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_detail_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';

class ArticleContentSurface extends StatelessWidget {
  const ArticleContentSurface({
    super.key,
    required this.child,
    this.highlighted = false,
    this.padding,
    this.backgroundColor,
  });

  final Widget child;
  final bool highlighted;
  final EdgeInsets? padding;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final panelColor =
        backgroundColor ??
        CupertinoColors.systemBackground.resolveFrom(context);
    final borderColor = highlighted
        ? AppColors.iosAccent(context)
        : CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.14);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: borderColor),
      ),
      child: child,
    );
  }
}

class ArticleContentBlockRenderer extends StatelessWidget {
  const ArticleContentBlockRenderer({
    super.key,
    required this.block,
    this.highlighted = false,
    this.onTap,
    this.backgroundColor,
    this.padding,
  });

  final ArticleContentBlockView block;
  final bool highlighted;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    final sectionHeadingLineHeight = articleBodyLineHeight() * 0.72;
    final titleColor = CupertinoColors.label.resolveFrom(context);
    final bodyColor = CupertinoColors.secondaryLabel.resolveFrom(context);
    final accent = AppColors.iosAccent(context);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ArticleContentSurface(
        highlighted: highlighted,
        backgroundColor: backgroundColor,
        padding: padding,
        child: switch (block.type) {
          'heading_2' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.xl,
              fontWeight: AppTypography.semiBold,
              height: articleBodyLineHeight(),
            ),
          ),
          'heading_3' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
              height: AppSpacing.textLineHeightHeadline,
            ),
          ),
          'section_heading' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.xl + 2,
              fontWeight: AppTypography.bold,
              height: sectionHeadingLineHeight,
              letterSpacing: 0.18,
            ),
          ),
          'image' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AspectRatio(
                aspectRatio: 4 / 3,
                child: ArticleAdaptiveImage(imageUrl: block.imageUrl ?? ''),
              ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: articleCaptionSpacing()),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                    height: articleCaptionLineHeight(),
                  ),
                ),
              ],
            ],
          ),
          'ordered_item' => Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: AppSpacing.twentyEight,
                height: AppSpacing.twentyEight,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.radiusNinetyNine,
                  ),
                ),
                child: Text(
                  '${block.orderedIndex ?? 1}',
                  style: TextStyle(
                    color: accent,
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Text(
                  block.body,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.base,
                    height: articleBodyLineHeight(),
                  ),
                ),
              ),
            ],
          ),
          'bullet_item' => Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
                child: Container(
                  width: AppSpacing.sm,
                  height: AppSpacing.sm,
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(AppSpacing.xs),
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Text(
                  block.body,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.base,
                    height: articleBodyLineHeight(),
                  ),
                ),
              ),
            ],
          ),
          'wrapped_paragraph' => ArticleWrappedParagraph(
            imageUrl: block.imageUrl ?? '',
            body: block.body,
            leadingText: block.leadingText,
            trailingText: block.trailingText,
            imageLayout: block.imageLayout,
            caption: block.caption ?? '',
          ),
          'section' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if ((block.imageUrl ?? '').isNotEmpty) ...[
                AspectRatio(
                  aspectRatio: 16 / 10,
                  child: ArticleAdaptiveImage(imageUrl: block.imageUrl!),
                ),
                SizedBox(height: articleChapterSpacing()),
              ],
              if (block.title.trim().isNotEmpty) ...[
                Text(
                  block.title,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.xl,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
              ],
              if (block.body.trim().isNotEmpty)
                Text(
                  block.body,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.base,
                    height: articleBodyLineHeight(),
                  ),
                ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: articleCaptionSpacing()),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                    height: articleCaptionLineHeight(),
                  ),
                ),
              ],
            ],
          ),
          _ => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.base,
              height: articleBodyLineHeight(),
            ),
          ),
        },
      ),
    );
  }
}

/// 缺席态语义 key（GWT-016）：图片引用无法解析出交付 URL 属于工程缺陷，
/// 与「加载中占位」「网络加载失败」互不混同，供测试与设备 UAT 区分。
const ValueKey<String> articleImageSourceAbsentKey = ValueKey<String>(
  'article-image-source-absent',
);

/// 文章图片加载体验语义 key（GWT-016）：
/// 静默占位（阈值内零动效）、超阈值指示、成功呈现、失败重试入口。
const ValueKey<String> articleImageSilentPlaceholderKey = ValueKey<String>(
  'article-image-silent-placeholder',
);
const ValueKey<String> articleImageDelayedIndicatorKey = ValueKey<String>(
  'article-image-delayed-indicator',
);
const ValueKey<String> articleImagePresentedContentKey = ValueKey<String>(
  'article-image-presented-content',
);
const ValueKey<String> articleImageFailedSurfaceKey = ValueKey<String>(
  'article-image-failed-surface',
);
const ValueKey<String> articleImageRetryKey = ValueKey<String>(
  'article-image-retry',
);

class ArticleAdaptiveImage extends ConsumerStatefulWidget {
  const ArticleAdaptiveImage({
    super.key,
    required this.imageUrl,
    this.signedDeliveryUrl = '',
    this.signedCacheIdentity = '',
  });

  static const String diagnosticSchemePrefix = 'diagnostic://pageflip/';

  final String imageUrl;

  /// 已换签的私有交付地址（DEC-033）。在场时跳过公开候选推导单候选直传，
  /// 文章特有的加载体验状态机保持不变——换签不得让消费面换一套观感。
  final String signedDeliveryUrl;

  /// 稳定资产身份缓存键。签名 query 随 TTL 轮换，不参与缓存键。
  final String signedCacheIdentity;

  @override
  ConsumerState<ArticleAdaptiveImage> createState() =>
      _ArticleAdaptiveImageState();
}

enum _ArticleImagePresentation { loading, ready, failed }

class _ArticleAdaptiveImageState extends ConsumerState<ArticleAdaptiveImage> {
  Timer? _indicatorDelayTimer;
  Timer? _indicatorMinDisplayTimer;
  _ArticleImagePresentation _presentation = _ArticleImagePresentation.loading;
  bool _indicatorVisible = false;
  bool _loadResolved = false;
  DateTime? _indicatorShownAt;
  int _loadGeneration = 0;
  List<String> _lastCandidates = const <String>[];

  @override
  void initState() {
    super.initState();
    _beginLoadingGeneration();
  }

  @override
  void didUpdateWidget(covariant ArticleAdaptiveImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.imageUrl.trim() != widget.imageUrl.trim()) {
      _beginLoadingGeneration();
    }
  }

  @override
  void dispose() {
    _cancelTimers();
    super.dispose();
  }

  void _beginLoadingGeneration({bool immediateIndicator = false}) {
    _cancelTimers();
    _loadGeneration += 1;
    _presentation = _ArticleImagePresentation.loading;
    _loadResolved = false;
    _indicatorVisible = immediateIndicator;
    _indicatorShownAt = immediateIndicator ? DateTime.now() : null;
    if (immediateIndicator) {
      return;
    }
    final generation = _loadGeneration;
    _indicatorDelayTimer = Timer(
      ImmersiveMediaWaitMotion.imageIndicatorDelay,
      () {
        if (!mounted || generation != _loadGeneration || _loadResolved) {
          return;
        }
        setState(() {
          _indicatorVisible = true;
          _indicatorShownAt = DateTime.now();
        });
      },
    );
  }

  void _resolveLoad(
    int generation,
    _ArticleImagePresentation terminalPresentation, {
    bool deferImmediatePresentation = false,
  }) {
    if (!mounted || generation != _loadGeneration || _loadResolved) {
      return;
    }
    _loadResolved = true;
    _indicatorDelayTimer?.cancel();

    void present() {
      if (!mounted || generation != _loadGeneration) {
        return;
      }
      setState(() {
        _presentation = terminalPresentation;
        _indicatorVisible = false;
      });
    }

    final shownAt = _indicatorShownAt;
    final remaining = shownAt == null
        ? Duration.zero
        : ImmersiveMediaWaitMotion.remainingIndicatorDisplay(shownAt);
    if (remaining > Duration.zero) {
      _indicatorMinDisplayTimer?.cancel();
      _indicatorMinDisplayTimer = Timer(remaining, present);
      return;
    }
    if (deferImmediatePresentation) {
      WidgetsBinding.instance.addPostFrameCallback((_) => present());
      return;
    }
    present();
  }

  void _onLoadSucceeded(int generation) {
    _resolveLoad(generation, _ArticleImagePresentation.ready);
  }

  void _onLoadFailed(int generation, Object _) {
    _resolveLoad(
      generation,
      _ArticleImagePresentation.failed,
      deferImmediatePresentation: true,
    );
  }

  void _retry() {
    // 同一候选的显式恢复动作：清除负缓存后用新 generation 重建真实
    // AppCachedNetworkImage 链路；重试立即给反馈，避免用户怀疑没有点中。
    for (final candidate in _lastCandidates) {
      MediaLoadFailureCache.instance.clearIdentity(candidate);
    }
    setState(() {
      _beginLoadingGeneration(immediateIndicator: true);
    });
  }

  void _cancelTimers() {
    _indicatorDelayTimer?.cancel();
    _indicatorMinDisplayTimer?.cancel();
    _indicatorDelayTimer = null;
    _indicatorMinDisplayTimer = null;
  }

  @override
  Widget build(BuildContext context) {
    final resolvedImageUrl = widget.imageUrl.trim();
    if (resolvedImageUrl.isEmpty || resolvedImageUrl.startsWith('asset://')) {
      // 空引用或未被 manifest/端点解析的 asset:// 残留：缺席态。
      return _ArticleImageSourceAbsent(reference: resolvedImageUrl);
    }
    if (resolvedImageUrl.startsWith(
      ArticleAdaptiveImage.diagnosticSchemePrefix,
    )) {
      return _ArticleDiagnosticImage(
        label: resolvedImageUrl.substring(
          ArticleAdaptiveImage.diagnosticSchemePrefix.length,
        ),
      );
    }
    if (isLocalFileImageSource(resolvedImageUrl)) {
      // 创作预览/编辑器面板的本地文件路径：不经公开媒体交付解析。
      final localPath = resolvedImageUrl.startsWith('file://')
          ? Uri.parse(resolvedImageUrl).toFilePath()
          : resolvedImageUrl;
      return Image(
        image: localFileImageProvider(localPath),
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
        errorBuilder: (context, error, stackTrace) => const KeyedSubtree(
          key: appImageLoadErrorKey,
          child: _ArticleImageUnavailableSurface(),
        ),
      );
    }
    final signedDeliveryUrl = widget.signedDeliveryUrl.trim();
    if (signedDeliveryUrl.isNotEmpty) {
      // 短签地址已由协调器校验：不进入公开候选推导，也不经 CDN 变体处理。
      return _buildNetworkImage(
        context,
        <String>[signedDeliveryUrl],
        forceFailed: false,
        cacheKey: widget.signedCacheIdentity.trim(),
      );
    }
    // 端点单源：只消费 provider 注入的媒体端点。provider 为 null 表示
    // 端点缺席，不允许 resolver 内部回退到全局静态形成第二真相源。
    final endpointConfig = ref.watch(mediaEndpointConfigProvider);
    final imageCandidates = endpointConfig == null
        ? const <String>[]
        : resolveContentMediaUrlCandidates(
            resolvedImageUrl,
            endpointConfig: endpointConfig,
          );
    final httpCandidates = imageCandidates
        .where(
          (candidate) =>
              candidate.startsWith('http://') ||
              candidate.startsWith('https://'),
        )
        .toList(growable: false);
    if (httpCandidates.isEmpty) {
      // media object key 无法解析出交付 URL（媒体端点未注入）：缺席态，
      // 不得退化为本地文件加载去制造一个假的「加载失败」。
      return _ArticleImageSourceAbsent(reference: resolvedImageUrl);
    }
    if (!listEquals(_lastCandidates, httpCandidates)) {
      _lastCandidates = httpCandidates;
    }
    final hasActiveFailure = MediaLoadFailureCache.instance.shouldSkipNetwork(
      httpCandidates.first,
    );
    return _buildNetworkImage(
      context,
      httpCandidates,
      forceFailed: hasActiveFailure,
    );
  }

  Widget _buildNetworkImage(
    BuildContext context,
    List<String> candidates, {
    required bool forceFailed,
    String cacheKey = '',
  }) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final presentation = forceFailed && !_loadResolved
        ? _ArticleImagePresentation.failed
        : _presentation;
    final transitionDuration = reduceMotion
        ? ImmersiveMediaWaitMotion.reducedMotionTransition
        : _indicatorShownAt != null
        ? ImmersiveMediaWaitMotion.crossFade
        : ImmersiveMediaWaitMotion.quickReveal;
    final generation = _loadGeneration;
    final image = AppCachedNetworkImage(
      key: ValueKey<String>('article-image-load-$generation'),
      imageUrl: candidates.first,
      imageUrlCandidates: candidates,
      cacheKey: cacheKey.isEmpty ? null : cacheKey,
      fit: BoxFit.cover,
      onLoadSucceeded: () => _onLoadSucceeded(generation),
      onLoadFailed: (error) => _onLoadFailed(generation, error),
      // 底层 placeholder/errorWidget 仅向文章状态机回报语义；可见状态层
      // 由下方 Stack 统一呈现，避免 CachedNetworkImage 与文章层双重动效。
      placeholder: const SizedBox.expand(),
      errorWidget: const SizedBox.expand(),
    );
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        // 网络组件始终保留在树中完成加载；成功前透明，不参与几何。
        AnimatedOpacity(
          key: articleImagePresentedContentKey,
          opacity: presentation == _ArticleImagePresentation.ready ? 1 : 0,
          duration: transitionDuration,
          curve: Curves.easeOut,
          child: image,
        ),
        Positioned.fill(
          child: IgnorePointer(
            ignoring: presentation != _ArticleImagePresentation.failed,
            child: AnimatedSwitcher(
              duration: reduceMotion
                  ? ImmersiveMediaWaitMotion.reducedMotionTransition
                  : ImmersiveMediaWaitMotion.indicatorFadeIn,
              reverseDuration: reduceMotion
                  ? ImmersiveMediaWaitMotion.reducedMotionTransition
                  : ImmersiveMediaWaitMotion.crossFade,
              switchInCurve: Curves.easeOut,
              switchOutCurve: Curves.easeIn,
              child: presentation == _ArticleImagePresentation.ready
                  ? const SizedBox.shrink(
                      key: ValueKey<String>('article-image-status-ready'),
                    )
                  : presentation == _ArticleImagePresentation.failed
                  ? _ArticleImageRetrySurface(onRetry: _retry)
                  : _indicatorVisible
                  ? const _ArticleImageDelayedIndicator()
                  : const _ArticleImageSilentPlaceholder(),
            ),
          ),
        ),
      ],
    );
  }
}

class _ArticleImageSilentPlaceholder extends StatelessWidget {
  const _ArticleImageSilentPlaceholder();

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      key: articleImageSilentPlaceholderKey,
      color: AppColors.iosGroupedSurface(context),
    );
  }
}

class _ArticleImageDelayedIndicator extends StatelessWidget {
  const _ArticleImageDelayedIndicator();

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      key: articleImageDelayedIndicatorKey,
      color: AppColors.iosGroupedSurface(context),
      child: Center(
        child: Opacity(
          opacity: 0.48,
          child: AppRequestFeedback.inline(
            indicatorColor: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}

class _ArticleImageRetrySurface extends StatelessWidget {
  const _ArticleImageRetrySurface({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      key: articleImageFailedSurfaceKey,
      color: AppColors.iosGroupedSurface(context),
      child: Center(
        child: CupertinoButton(
          key: articleImageRetryKey,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.intraGroupSm,
          ),
          onPressed: onRetry,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.image_not_supported_outlined,
                color: AppColors.iosSecondaryLabel(context),
                size: AppSpacing.twenty,
              ),
              SizedBox(height: AppSpacing.xs),
              Text(
                ContentText.imageLoadFailed,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.iosSecondaryLabel(context),
                  fontSize: AppTypography.iosCaption1,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                ContentText.tryAgain,
                style: TextStyle(
                  color: AppColors.iosAccent(context),
                  fontSize: AppTypography.iosCaption1,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 缺席态：用户视觉与失败一致，语义标识独立并经异常遥测留证据（一次）。
class _ArticleImageSourceAbsent extends ConsumerStatefulWidget {
  const _ArticleImageSourceAbsent({required this.reference});

  final String reference;

  @override
  ConsumerState<_ArticleImageSourceAbsent> createState() =>
      _ArticleImageSourceAbsentState();
}

class _ArticleImageSourceAbsentState
    extends ConsumerState<_ArticleImageSourceAbsent> {
  bool _reported = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _reported) {
        return;
      }
      _reported = true;
      ref
          .read(exceptionTelemetryPortProvider)
          .recordHandledException(
            source: 'content.post.article_adaptive_image',
            error: StateError(
              'article image source absent: '
              '${widget.reference.isEmpty ? '<empty>' : widget.reference}',
            ),
            stackTrace: StackTrace.current,
            operationId: 'app.content.article_image_resolve',
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    return const KeyedSubtree(
      key: articleImageSourceAbsentKey,
      child: _ArticleImageUnavailableSurface(),
    );
  }
}

/// 缺席/本地失败共用的不可用视觉：icon + 文案，同 AppCachedNetworkImage
/// 失败态风格（设计 token，不硬编码颜色）。
class _ArticleImageUnavailableSurface extends StatelessWidget {
  const _ArticleImageUnavailableSurface();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.iosGroupedSurface(context),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.image_not_supported_outlined,
              color: AppColors.iosSecondaryLabel(context),
              size: AppSpacing.twenty,
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              ContentText.imageLoadFailed,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosCaption1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ArticleDiagnosticImage extends StatelessWidget {
  const _ArticleDiagnosticImage({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final palette = <Color>[
      AppColors.primaryColor,
      AppColors.warning,
      AppColors.success,
    ];
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: palette,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          Align(
            alignment: Alignment.topLeft,
            child: FractionallySizedBox(
              widthFactor: 0.52,
              heightFactor: 0.46,
              child: ColoredBox(color: AppColors.white.withValues(alpha: 0.28)),
            ),
          ),
          Align(
            alignment: Alignment.bottomRight,
            child: FractionallySizedBox(
              widthFactor: 0.42,
              heightFactor: 0.5,
              child: ColoredBox(color: AppColors.black.withValues(alpha: 0.18)),
            ),
          ),
          Center(
            child: Text(
              'PAGE $label',
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.iosTitle3,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class ArticleWrappedParagraph extends StatelessWidget {
  const ArticleWrappedParagraph({
    super.key,
    required this.imageUrl,
    required this.body,
    this.binding = const MediaDeliveryBinding.absent(),
    this.leadingText = '',
    this.trailingText = '',
    required this.imageLayout,
    this.caption = '',
    this.figureAspectRatio,
    this.metrics,
    this.onImageTap,
  });

  final String imageUrl;

  /// 环绕排版内嵌图的 typed 交付绑定（DEC-033）。与整宽内嵌图同一分流入口，
  /// 私有页经协调器换签后仍由 [ArticleAdaptiveImage] 渲染，保住文章自有的
  /// 静默占位与延迟指示体验。
  final MediaDeliveryBinding binding;
  final String body;
  final String leadingText;
  final String trailingText;
  final String imageLayout;
  final String caption;
  final VoidCallback? onImageTap;

  /// 图片占位比例（REQ-017）：由调用方经 resolveArticleFigureAspectRatio
  /// 决定后传入，与分页测量同源；null 回退 metrics 后备比例。
  final double? figureAspectRatio;
  final ArticleCanvasMetrics? metrics;

  @override
  Widget build(BuildContext context) {
    final textStyle = TextStyle(
      color: CupertinoColors.label.resolveFrom(context),
      fontSize: AppTypography.base,
      height: articleBodyLineHeight(),
    );
    final captionStyle = TextStyle(
      color: CupertinoColors.secondaryLabel.resolveFrom(context),
      fontSize: AppTypography.sm,
      height: articleCaptionLineHeight(),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final resolvedMetrics = metrics ?? ArticleCanvasMetrics.snapshot();
        final wrap = resolveArticleWrapLayout(
          ArticleWrapLayoutInput(
            body: body,
            leadingText: leadingText.isEmpty ? null : leadingText,
            trailingText: trailingText.isEmpty ? null : trailingText,
            rowContentWidth: constraints.maxWidth,
            bodyStyle: textStyle,
            captionText: caption,
            captionStyle: captionStyle,
            captionPlaceholderWhenEmpty: false,
            imageLayout: imageLayout,
            figureAspectRatio: figureAspectRatio,
            metrics: resolvedMetrics,
          ),
        );
        final textColumn = Expanded(
          child: Text(
            wrap.leadingText.trim().isEmpty ? body : wrap.leadingText.trim(),
            style: textStyle,
          ),
        );
        // Padding(top: halfLeading) 让图片视觉顶部与文字视觉顶部对齐。
        // Text widget 的第一行文字有 halfLeading 的顶部空白，
        // 图片需要同样的偏移才能视觉对齐。
        final image = Padding(
          padding: EdgeInsets.only(top: wrap.layout.textHalfLeading),
          child: SizedBox(
            width: wrap.layout.imageWidth,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                SizedBox(
                  width: wrap.layout.imageWidth,
                  height: wrap.layout.imageHeight,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: onImageTap,
                    child: mediaDeliveryImage(
                      binding: binding.hasRenderableSource
                          ? binding
                          : MediaDeliveryBinding.previousPublic(
                              publicUrl: imageUrl,
                            ),
                      kind: MediaDeliveryKind.image,
                      publicBuilder: (context, publicUrl) =>
                          ArticleAdaptiveImage(imageUrl: publicUrl),
                      signedReadyBuilder:
                          (context, deliveryUrl, cacheIdentity) =>
                              ArticleAdaptiveImage(
                                imageUrl: imageUrl,
                                signedDeliveryUrl: deliveryUrl,
                                signedCacheIdentity: cacheIdentity,
                              ),
                    ),
                  ),
                ),
                if (caption.trim().isNotEmpty) ...<Widget>[
                  SizedBox(height: wrap.layout.captionSpacing),
                  Text(
                    caption.trim(),
                    textAlign: TextAlign.center,
                    style: captionStyle,
                  ),
                ],
              ],
            ),
          ),
        );
        final rowChildren = imageLayout == 'wrapRight'
            ? <Widget>[textColumn, SizedBox(width: wrap.layout.sideGap), image]
            : <Widget>[image, SizedBox(width: wrap.layout.sideGap), textColumn];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: rowChildren,
            ),
            if (wrap.trailingText.trim().isNotEmpty) ...[
              SizedBox(height: wrap.layout.trailingSpacing),
              Text(wrap.trailingText.trim(), style: textStyle),
            ],
          ],
        );
      },
    );
  }
}
