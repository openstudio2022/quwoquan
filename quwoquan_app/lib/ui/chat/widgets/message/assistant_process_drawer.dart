import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';

class AssistantProcessDrawer extends StatefulWidget {
  const AssistantProcessDrawer({
    super.key,
    required this.viewModel,
    this.initiallyExpanded = false,
    this.onReferenceUrlTap,
  });

  final AssistantJourneyViewModel viewModel;
  final bool initiallyExpanded;
  final void Function(String url)? onReferenceUrlTap;

  @override
  State<AssistantProcessDrawer> createState() => _AssistantProcessDrawerState();
}

class _AssistantProcessDrawerState extends State<AssistantProcessDrawer> {
  bool _expanded = false;
  final Set<int> _expandedBlockIndices = <int>{};

  AssistantJourneyViewModel get _viewModel => widget.viewModel;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  bool get _isLongWaitWithoutProgress {
    if (!_viewModel.isRunning) return false;
    return _viewModel.elapsedMs >= 6000 && _viewModel.blocks.isEmpty;
  }

  String _waitReassuranceText() {
    final elapsed = _viewModel.elapsedMs;
    if (elapsed >= 20000) {
      return UITextConstants.assistantProcessRecoveryReassurance;
    }
    if (elapsed >= 12000) {
      return UITextConstants.assistantProcessHandoffReassurance;
    }
    return UITextConstants.assistantProcessLongWaitReassurance;
  }

  int _elapsedSeconds() {
    final elapsed = _viewModel.elapsedMs;
    if (elapsed <= 0) return 0;
    final roundedSeconds = (elapsed / 1000).round();
    return roundedSeconds <= 0 ? 1 : roundedSeconds;
  }

  String _referenceCountLabel(int count) {
    return UITextConstants.assistantProcessReferenceCountTemplate.replaceFirst(
      '%s',
      count.toString(),
    );
  }

  int _summaryDocumentCount() {
    if (_viewModel.processedDocumentCount > 0) {
      return _viewModel.processedDocumentCount;
    }
    if (_viewModel.acceptedDocumentCount > 0) {
      return _viewModel.acceptedDocumentCount;
    }
    return _viewModel.referenceCount;
  }

  String _summaryHeaderLabel() {
    if (!_viewModel.isRunning && _viewModel.finalAnswerReady) {
      final documentCount = _summaryDocumentCount();
      final elapsedSeconds = _elapsedSeconds();
      if (documentCount > 0 && elapsedSeconds > 0) {
        return UITextConstants.assistantProcessCompletedSummaryFullTemplate
            .replaceFirst('%s', documentCount.toString())
            .replaceFirst('%s', elapsedSeconds.toString());
      }
      if (documentCount > 0) {
        return UITextConstants
            .assistantProcessCompletedSummaryReferencesTemplate
            .replaceFirst('%s', documentCount.toString());
      }
      if (elapsedSeconds > 0) {
        return UITextConstants.assistantProcessCompletedSummaryElapsedTemplate
            .replaceFirst('%s', elapsedSeconds.toString());
      }
      return UITextConstants.assistantProcessCompletedSummary;
    }
    if (_viewModel.summary.isNotEmpty) {
      return _viewModel.referenceCount > 0
          ? '${_viewModel.summary} · ${_referenceCountLabel(_viewModel.referenceCount)}'
          : _viewModel.summary;
    }
    if (_viewModel.referenceCount > 0) {
      return _referenceCountLabel(_viewModel.referenceCount);
    }
    return _viewModel.activeStageLabel.isNotEmpty
        ? _viewModel.activeStageLabel
        : UITextConstants.assistantPhaseCompleted;
  }

  String _headerLabel() {
    if (_viewModel.isRunning && _viewModel.activeStageLabel.isNotEmpty) {
      return _viewModel.activeStageLabel;
    }
    if (!_viewModel.isRunning && _viewModel.finalAnswerReady) {
      return _summaryHeaderLabel();
    }
    if (!_viewModel.isRunning && !_expanded) {
      return _summaryHeaderLabel();
    }
    if (_viewModel.summary.isNotEmpty) {
      return _viewModel.summary;
    }
    return _summaryHeaderLabel();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final textColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryTextColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final accentColor = AppColorsFunctional.getColor(isDark, ColorType.primary);
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.xs),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: borderColor, width: AppSpacing.one / 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildHeader(
            textColor: textColor,
            secondaryTextColor: secondaryTextColor,
            accentColor: accentColor,
          ),
          if (_expanded)
            _buildBody(
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
              accentColor: accentColor,
            ),
        ],
      ),
    );
  }

  Widget _buildHeader({
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    final monochrome = Color.lerp(secondaryTextColor, accentColor, 0.22)!;
    return GestureDetector(
      key: TestKeys.assistantProcessHeader,
      onTap: () => setState(() => _expanded = !_expanded),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupSm,
        ),
        child: Row(
          children: [
            if (!_viewModel.isRunning)
              Padding(
                padding: EdgeInsets.only(right: AppSpacing.xs),
                child: Icon(
                  CupertinoIcons.checkmark_circle_fill,
                  size: AppTypography.base,
                  color: accentColor,
                ),
              ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Flexible(
                        child: Text(
                          _headerLabel(),
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            fontWeight: FontWeight.w500,
                            color: textColor,
                            height: AppTypography.bodyLineHeight,
                          ),
                        ),
                      ),
                      if (_viewModel.isRunning)
                        Padding(
                          padding: EdgeInsets.only(left: AppSpacing.xs),
                          child: _BreathingCapsule(color: monochrome),
                        ),
                    ],
                  ),
                  if (_isLongWaitWithoutProgress)
                    Padding(
                      padding: EdgeInsets.only(top: AppSpacing.xs / 2),
                      child: Text(
                        _waitReassuranceText(),
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: secondaryTextColor.withValues(alpha: 0.85),
                          height: AppTypography.bodyLineHeight,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Icon(
              _expanded
                  ? CupertinoIcons.chevron_up
                  : CupertinoIcons.chevron_down,
              size: AppTypography.smPlus,
              color: secondaryTextColor,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody({
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.sm,
        right: AppSpacing.sm,
        bottom: AppSpacing.intraGroupSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: double.infinity,
            height: AppSpacing.one / 2,
            color: secondaryTextColor.withValues(alpha: 0.15),
          ),
          SizedBox(height: AppSpacing.xs),
          if (_viewModel.stages.isNotEmpty)
            _buildStageStrip(
              secondaryTextColor: secondaryTextColor,
              accentColor: accentColor,
            ),
          if (_viewModel.stages.isNotEmpty && _viewModel.blocks.isNotEmpty)
            SizedBox(height: AppSpacing.xs),
          for (var i = 0; i < _viewModel.blocks.length; i++)
            _buildBlock(
              index: i,
              block: _viewModel.blocks[i],
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
              accentColor: accentColor,
            ),
        ],
      ),
    );
  }

  Widget _buildStageStrip({
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: _viewModel.stages
          .map(
            (stage) => Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.xs,
                vertical: AppSpacing.xs / 2,
              ),
              decoration: BoxDecoration(
                color:
                    _stageColor(
                      stage.status,
                      accentColor: accentColor,
                      secondaryTextColor: secondaryTextColor,
                    ).withValues(
                      alpha: stage.isActive
                          ? 0.18
                          : (stage.isResolved ? 0.12 : 0.08),
                    ),
                borderRadius: BorderRadius.circular(AppSpacing.sm),
              ),
              child: Text(
                stage.label,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: FontWeight.w500,
                  color: _stageColor(
                    stage.status,
                    accentColor: accentColor,
                    secondaryTextColor: secondaryTextColor,
                  ),
                  height: AppTypography.bodyLineHeight,
                ),
              ),
            ),
          )
          .toList(growable: false),
    );
  }

  Color _stageColor(
    JourneyStageStatus status, {
    required Color accentColor,
    required Color secondaryTextColor,
  }) {
    switch (status) {
      case JourneyStageStatus.active:
      case JourneyStageStatus.completed:
        return accentColor;
      case JourneyStageStatus.blocked:
        return AppColors.warning;
      case JourneyStageStatus.skipped:
      case JourneyStageStatus.pending:
      case JourneyStageStatus.unknown:
        return secondaryTextColor.withValues(alpha: 0.85);
    }
  }

  Widget _buildBlock({
    required int index,
    required AssistantJourneyBlockViewModel block,
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    if (!block.hasReferences) {
      return Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.three),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (block.headline.isNotEmpty)
              Text(
                block.headline,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: secondaryTextColor,
                  height: AppTypography.lineHeightRelaxed,
                ),
              ),
            if (block.detail.isNotEmpty)
              Padding(
                padding: EdgeInsets.only(
                  top: block.headline.isNotEmpty ? 4 : 0,
                ),
                child: Text(
                  block.detail,
                  style: TextStyle(
                    fontSize: AppTypography.xsPlus,
                    color: secondaryTextColor.withValues(alpha: 0.9),
                    height: AppTypography.lineHeightRelaxed,
                  ),
                ),
              ),
          ],
        ),
      );
    }
    return _buildCollapsibleReferenceBlock(
      index: index,
      icon: block.kind == AssistantJourneyBlockKind.searchSummary
          ? CupertinoIcons.search
          : CupertinoIcons.doc_text,
      label: block.headline,
      detail: block.detail,
      references: block.references,
      textColor: textColor,
      secondaryTextColor: secondaryTextColor,
      accentColor: accentColor,
    );
  }

  Widget _buildCollapsibleReferenceBlock({
    required int index,
    required IconData icon,
    required String label,
    required String detail,
    required List<AssistantJourneyReferenceViewModel> references,
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    final isExpanded = _expandedBlockIndices.contains(index);
    final sourceSummary = references
        .map((reference) => reference.source.trim())
        .where((source) => source.isNotEmpty)
        .toSet()
        .take(2)
        .join('、');
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              setState(() {
                if (isExpanded) {
                  _expandedBlockIndices.remove(index);
                } else {
                  _expandedBlockIndices.add(index);
                }
              });
            },
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.xs / 2),
              child: Row(
                children: [
                  Icon(icon, size: AppTypography.smPlus, color: accentColor),
                  SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      label.isNotEmpty
                          ? label
                          : _referenceCountLabel(references.length),
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w500,
                        color: textColor,
                      ),
                    ),
                  ),
                  Icon(
                    isExpanded
                        ? CupertinoIcons.chevron_up
                        : CupertinoIcons.chevron_down,
                    size: AppTypography.xsPlus,
                    color: secondaryTextColor,
                  ),
                ],
              ),
            ),
          ),
          if (detail.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(
                left: AppTypography.smPlus + AppSpacing.xs,
                bottom: AppSpacing.xs / 2,
              ),
              child: Text(
                detail,
                style: TextStyle(
                  fontSize: AppTypography.xsPlus,
                  color: secondaryTextColor,
                  height: AppTypography.bodyLineHeight,
                ),
              ),
            ),
          if (sourceSummary.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(
                left: AppTypography.smPlus + AppSpacing.xs,
                bottom: AppSpacing.xs / 2,
              ),
              child: Text(
                '来源：$sourceSummary',
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: secondaryTextColor.withValues(alpha: 0.8),
                  height: AppTypography.bodyLineHeight,
                ),
              ),
            ),
          if (isExpanded)
            Padding(
              padding: EdgeInsets.only(
                left: AppTypography.smPlus + AppSpacing.xs,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: references
                    .map(
                      (reference) => GestureDetector(
                        onTap: reference.url.isNotEmpty
                            ? () =>
                                  widget.onReferenceUrlTap?.call(reference.url)
                            : null,
                        behavior: HitTestBehavior.opaque,
                        child: Padding(
                          padding: EdgeInsets.only(bottom: AppSpacing.xs / 2),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  reference.source.trim().isNotEmpty
                                      ? '${reference.title} · ${reference.source}'
                                      : reference.title,
                                  style: TextStyle(
                                    fontSize: AppTypography.base,
                                    color: accentColor,
                                    decoration: TextDecoration.underline,
                                    decorationColor: accentColor.withValues(
                                      alpha: 0.4,
                                    ),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              if (reference.url.isNotEmpty)
                                Padding(
                                  padding: EdgeInsets.only(left: AppSpacing.xs),
                                  child: Icon(
                                    CupertinoIcons.arrow_up_right,
                                    size: AppTypography.xs,
                                    color: accentColor.withValues(alpha: 0.6),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    )
                    .toList(growable: false),
              ),
            ),
        ],
      ),
    );
  }
}

/// Breathing capsule: a rounded shape that smoothly stretches and contracts,
/// inspired by 元宝-style "circle → elongate right → elongate left → circle"
/// loop. Monochrome, calming, minimal.
class _BreathingCapsule extends StatefulWidget {
  const _BreathingCapsule({required this.color});

  final Color color;

  @override
  State<_BreathingCapsule> createState() => _BreathingCapsuleState();
}

class _BreathingCapsuleState extends State<_BreathingCapsule>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = _controller.value;
        // 0→0.25: circle→elongate right
        // 0.25→0.5: elongate right→circle
        // 0.5→0.75: circle→elongate left
        // 0.75→1.0: elongate left→circle
        final double phase;
        if (t < 0.25) {
          phase = Curves.easeInOut.transform(t * 4);
        } else if (t < 0.5) {
          phase = Curves.easeInOut.transform(1 - (t - 0.25) * 4);
        } else if (t < 0.75) {
          phase = -Curves.easeInOut.transform((t - 0.5) * 4);
        } else {
          phase = -Curves.easeInOut.transform(1 - (t - 0.75) * 4);
        }
        final w = 10.0 + phase.abs() * 6;
        final h = 10.0 - phase.abs() * 2;
        final dx = phase * 2;
        final opacity = 0.5 + (1 - phase.abs()) * 0.5;
        return SizedBox(
          width: AppSpacing.eighteen,
          height: AppSpacing.fourteen,
          child: Center(
            child: Transform.translate(
              offset: Offset(dx, 0),
              child: Opacity(
                opacity: opacity,
                child: Container(
                  width: w,
                  height: h,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(h / 2),
                    color: widget.color.withValues(alpha: 0.7),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Three-dot pulse animation.
/// Used as the "waiting" indicator for Phase 2+ processing states.
class _ThreeDotPulse extends StatefulWidget {
  const _ThreeDotPulse({required this.color, this.size = 3});

  final Color color;
  final double size;

  @override
  State<_ThreeDotPulse> createState() => _ThreeDotPulseState();
}

class _ThreeDotPulseState extends State<_ThreeDotPulse>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            final delay = i * 0.22;
            final shifted = (_controller.value + 1 - delay) % 1;
            final opacity = shifted < 0.5
                ? 0.28 + 0.72 * (shifted * 2)
                : 0.28 + 0.72 * (1 - (shifted - 0.5) * 2);
            final scale = 0.78 + shifted * 0.22;
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 1),
              child: Transform.scale(
                scale: scale,
                child: Opacity(
                  opacity: opacity,
                  child: Container(
                    width: widget.size,
                    height: widget.size,
                    decoration: BoxDecoration(
                      color: widget.color,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }
}

/// Fade-and-slide-in animation for streaming flow event rows.
/// Each row plays its entrance animation once on first build, giving
/// a progressive "streaming" feel similar to 元宝.
class _FlowEventFadeIn extends StatefulWidget {
  const _FlowEventFadeIn({required this.child});

  final Widget child;

  @override
  State<_FlowEventFadeIn> createState() => _FlowEventFadeInState();
}

class _FlowEventFadeInState extends State<_FlowEventFadeIn>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
    _opacity = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.18),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: SlideTransition(position: _slide, child: widget.child),
    );
  }
}
