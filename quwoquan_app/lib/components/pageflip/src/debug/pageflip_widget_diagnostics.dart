import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_engine.dart';
import 'package:quwoquan_app/components/pageflip/src/debug/pageflip_diagnostics_shared.dart';
import 'package:quwoquan_app/components/pageflip/src/widget/pageflip_widget.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_theme.dart';

class PageflipWidgetDiagnosticsApp extends StatefulWidget {
  const PageflipWidgetDiagnosticsApp({super.key});

  @override
  State<PageflipWidgetDiagnosticsApp> createState() =>
      _PageflipWidgetDiagnosticsAppState();
}

class _PageflipWidgetDiagnosticsAppState
    extends State<PageflipWidgetDiagnosticsApp> {
  late final _pages = buildPageflipDiagnosticPages();
  late final PageflipEngine _engine = PageflipEngine(
    pageCount: 5,
    initialPage: 2,
  );
  final ValueNotifier<PageflipWidgetDebugState?> _debugNotifier =
      ValueNotifier<PageflipWidgetDebugState?>(null);
  PageflipWidgetDebugState? _pendingDebugState;
  bool _debugUpdateScheduled = false;

  @override
  void dispose() {
    _debugNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(
      context,
      kPageflipDiagnosticsTemplate,
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
              return Padding(
                padding: kPageflipDiagnosticsViewportPadding,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    PageflipWidget(
                      engine: _engine,
                      pageAspectRatio: metrics.aspectRatio,
                      stagePadding: pagePadding,
                      stageColor: palette.paperColor,
                      onDebugStateChanged: (debugState) {
                        _pendingDebugState = debugState;
                        if (_debugUpdateScheduled) {
                          return;
                        }
                        _debugUpdateScheduled = true;
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          _debugUpdateScheduled = false;
                          if (!mounted || _pendingDebugState == null) {
                            return;
                          }
                          final nextDebugState = _pendingDebugState;
                          _pendingDebugState = null;
                          _debugNotifier.value = nextDebugState;
                        });
                      },
                      pageBuilder: (context, pageIndex) {
                        return PageflipDiagnosticsParityPage(
                          pages: _pages,
                          pageIndex: pageIndex,
                          metrics: metrics,
                          showFooterPageLabel: true,
                        );
                      },
                    ),
                    const Positioned.fill(
                      child: IgnorePointer(
                        child: _PageflipWidgetAcceptanceBanner(),
                      ),
                    ),
                    Positioned.fill(
                      child: IgnorePointer(
                        child:
                            ValueListenableBuilder<PageflipWidgetDebugState?>(
                              valueListenable: _debugNotifier,
                              builder: (context, debugState, _) {
                                return _PageflipWidgetDiagnosticsHeader(
                                  debugState: debugState,
                                );
                              },
                            ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _PageflipWidgetDiagnosticsHeader extends StatelessWidget {
  const _PageflipWidgetDiagnosticsHeader({required this.debugState});

  final PageflipWidgetDebugState? debugState;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          0,
        ),
        child: Align(
          alignment: Alignment.topRight,
          child: debugState == null
              ? const SizedBox.shrink()
              : ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 300),
                  child: _PageflipWidgetDebugCard(debugState: debugState!),
                ),
        ),
      ),
    );
  }
}

class _PageflipWidgetAcceptanceBanner extends StatelessWidget {
  const _PageflipWidgetAcceptanceBanner();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          AppSpacing.containerXs,
          0,
        ),
        child: DecoratedBox(
          key: const ValueKey('pageflip_widget_acceptance_banner'),
          decoration: BoxDecoration(
            color: AppColors.primaryColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            border: Border.all(
              color: AppColors.primaryColor.withValues(alpha: 0.35),
              width: AppSpacing.hairline,
            ),
          ),
          child: const Padding(
            padding: EdgeInsets.all(AppSpacing.containerXs),
            child: Text(
              'ACCEPTANCE ENTRY\nUse tool/pageflip_widget_diagnostics_main.dart only.\nThis host validates the new PageflipWidget mesh mainline.',
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.iosCaption1,
                height: AppTypography.lineHeightTight,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PageflipWidgetDebugCard extends StatelessWidget {
  const _PageflipWidgetDebugCard({required this.debugState});

  final PageflipWidgetDebugState debugState;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      key: const ValueKey('pageflip_widget_debug_card'),
      decoration: BoxDecoration(
        color: AppColors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(
          color: AppColors.black.withValues(alpha: 0.14),
          width: AppSpacing.hairline,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.containerXs),
        child: DefaultTextStyle(
          style: const TextStyle(
            color: AppColors.black,
            fontSize: AppTypography.iosCaption2,
            height: AppTypography.lineHeightTight,
            fontFamily: 'SF Mono',
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              _DebugLine(
                label: 'scene',
                value:
                    'cur ${_pageLabel(debugState.currentPageIndex)} | turn ${_pageLabel(debugState.turningPageIndex)} | under ${_pageLabel(debugState.underlayPageIndex)} | cover ${_pageLabel(debugState.coveredPageIndex)}',
              ),
              _DebugLine(
                label: 'state',
                value:
                    'static ${_pageLabel(debugState.staticPageIndex)} | dir ${debugState.renderDirection?.name ?? '-'} | mesh ${debugState.meshReady ? 'ready' : 'wait'}',
              ),
              _DebugLine(
                label: 'request',
                value:
                    'r ${_pageLabel(debugState.requestedRectoPageIndex)} | v ${_pageLabel(debugState.requestedVersoPageIndex)} | b ${_pageLabel(debugState.requestedBottomPageIndex)}',
              ),
              _DebugLine(
                label: 'active',
                value:
                    'r ${_pageLabel(debugState.activeRectoPageIndex)} | v ${_pageLabel(debugState.activeVersoPageIndex)} | b ${_pageLabel(debugState.activeBottomPageIndex)}',
              ),
              _DebugLine(
                label: 'bundle',
                value:
                    'hf ${debugState.sessionPrefersHighFidelity ? 'on' : 'off'} | ${debugState.sessionHasBundle ? 'ready' : 'waiting'} | missing [${_pageList(debugState.missingSnapshotIndices)}]',
              ),
              _DebugLine(
                label: 'front',
                value: _rectLabel(debugState.frontBounds),
              ),
              _DebugLine(
                label: 'back',
                value: _rectLabel(debugState.backBounds),
              ),
              _DebugLine(
                label: 'guide',
                value:
                    'spine ${_metricLabel(debugState.spineDelta)} | seam ${_metricLabel(debugState.seamDelta)}',
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _pageLabel(int? index) => index == null ? '-' : (index + 1).toString();

  String _pageList(List<int> indices) {
    if (indices.isEmpty) {
      return '-';
    }
    return indices.map((index) => (index + 1).toString()).join(',');
  }

  String _metricLabel(double? value) {
    if (value == null) {
      return '-';
    }
    return value.toStringAsFixed(4);
  }

  String _rectLabel(Rect? rect) {
    if (rect == null) {
      return '-';
    }
    return [
      rect.left.toStringAsFixed(1),
      rect.top.toStringAsFixed(1),
      rect.width.toStringAsFixed(1),
      rect.height.toStringAsFixed(1),
    ].join(' / ');
  }
}

class _DebugLine extends StatelessWidget {
  const _DebugLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: Text('$label $value'),
    );
  }
}
