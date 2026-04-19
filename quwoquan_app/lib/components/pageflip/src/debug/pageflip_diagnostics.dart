import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/pageflip/src/scene/pageflip_scene.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class PageflipDiagnosticsApp extends StatefulWidget {
  const PageflipDiagnosticsApp({super.key});

  @override
  State<PageflipDiagnosticsApp> createState() => _PageflipDiagnosticsAppState();
}

class _PageflipDiagnosticsAppState extends State<PageflipDiagnosticsApp> {
  final ValueNotifier<PageflipScene?> _sceneNotifier = ValueNotifier<PageflipScene?>(null);
  PageflipScene? _pendingScene;
  bool _sceneUpdateScheduled = false;

  @override
  void dispose() {
    _sceneNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(
      context,
      ArticleTemplatePreset.tech,
    );
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: AppScaffold(
        body: ColoredBox(
          color: palette.paperColor,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final metrics = resolveArticleCanvasMetrics(
                context,
                constraints,
                variant: ArticleCanvasVariant.detail,
              );
              final pagePadding = articleReaderStagePagePadding();
              return Stack(
                fit: StackFit.expand,
                children: [
                  Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    child: ArticleReadOnlyBookDeck(
                      pages: _diagnosticPages(),
                      template: ArticleTemplatePreset.tech,
                      fontPreset: ArticleFontPreset.mono,
                      metrics: metrics,
                      pagePadding: pagePadding,
                      initialPage: 2,
                      coverUrl: '',
                      showFooterPageLabel: false,
                      onSceneChanged: (scene) {
                        _pendingScene = scene;
                        if (_sceneUpdateScheduled) {
                          return;
                        }
                        _sceneUpdateScheduled = true;
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          _sceneUpdateScheduled = false;
                          if (!mounted || _pendingScene == null) {
                            return;
                          }
                          final nextScene = _pendingScene;
                          _pendingScene = null;
                          _sceneNotifier.value = nextScene;
                        });
                      },
                    ),
                  ),
                  Positioned.fill(
                    child: IgnorePointer(
                      child: ValueListenableBuilder<PageflipScene?>(
                        valueListenable: _sceneNotifier,
                        builder: (context, scene, _) {
                          if (scene == null) {
                            return const SizedBox.shrink();
                          }
                          return _SamplingPointsOverlay(scene: scene);
                        },
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  List<ArticlePageData> _diagnosticPages() {
    return <ArticlePageData>[
      ArticlePageData(
        id: 'diag_0',
        title: 'SEAM TRACE / 01',
        body: 'page 1/5\n\nLEFT EDGE CHECK | FOLD CHECK | RIGHT EDGE CHECK',
      ),
      ArticlePageData(
        id: 'diag_1',
        title: 'SEAM TRACE / 02',
        body: 'page 2/5\n\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      ),
      ArticlePageData(
        id: 'diag_2',
        title: 'SEAM TRACE / 03',
        body: 'page 3/5\n\nBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
      ),
      ArticlePageData(
        id: 'diag_3',
        title: 'SEAM TRACE / 04',
        body: 'page 4/5\n\nCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC',
      ),
      ArticlePageData(
        id: 'diag_4',
        title: 'SEAM TRACE / 05',
        body: 'page 5/5\n\nDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD',
      ),
    ];
  }
}

class _SamplingPointsOverlay extends StatelessWidget {
  const _SamplingPointsOverlay({required this.scene});

  final PageflipScene scene;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final pageRect = scene.pageRect;
    final foldSample = _foldSamplePoint(scene);
    final edgeSample = Offset(
      pageRect.right - AppSpacing.iconLarge + AppSpacing.xs / 2,
      pageRect.center.dy,
    );
    final seamGuideX = foldSample.dx;
    final sampleRadius = AppSpacing.iconSmall / 2;
    return Stack(
      children: [
        Positioned(
          left: seamGuideX - AppSpacing.xs / 4,
          top: pageRect.top,
          child: Container(
            width: AppSpacing.xs / 2,
            height: pageRect.height,
            color: AppColors.error.withValues(alpha: 0.8),
          ),
        ),
        if (scene.renderFrame != null)
          Positioned(
            left: foldSample.dx - sampleRadius,
            top: foldSample.dy - sampleRadius,
            child: _SampleDot(
              label: 'fold',
              color: AppColors.warning,
              isDark: isDark,
            ),
          ),
        Positioned(
          left: edgeSample.dx - sampleRadius,
          top: edgeSample.dy - sampleRadius,
          child: _SampleDot(
            label: 'edge',
            color: AppColors.primaryColor,
            isDark: isDark,
          ),
        ),
      ],
    );
  }

  Offset _foldSamplePoint(PageflipScene scene) {
    final renderFrame = scene.renderFrame;
    if (renderFrame == null) {
      return scene.pageRect.center;
    }
    final pageRect = scene.pageRect;
    final basePivot = renderFrame.canonicalFrame.timeline.basePivot;
    return Offset(pageRect.left + basePivot, pageRect.center.dy);
  }
}

class _SampleDot extends StatelessWidget {
  const _SampleDot({
    required this.label,
    required this.color,
    required this.isDark,
  });

  final String label;
  final Color color;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: AppSpacing.iconSmall,
          height: AppSpacing.iconSmall,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.92),
            border: Border.all(
              color: isDark
                  ? AppColors.white.withValues(alpha: 0.35)
                  : AppColors.black.withValues(alpha: 0.35),
              width: AppSpacing.xs / 4,
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        DecoratedBox(
          decoration: BoxDecoration(
            color: (isDark ? AppColors.black : AppColors.white)
                .withValues(alpha: isDark ? 0.6 : 0.78),
            borderRadius: BorderRadius.circular(
              AppSpacing.borderRadius - AppSpacing.xs / 2,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.xs + AppSpacing.xs / 2,
              vertical: AppSpacing.xs / 2,
            ),
            child: Text(
              label,
              style: TextStyle(
                color: isDark ? AppColors.white : AppColors.black,
                fontSize: AppTypography.iosCaption2,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
