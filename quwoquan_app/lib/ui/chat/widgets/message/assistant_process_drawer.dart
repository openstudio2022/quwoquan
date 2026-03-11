import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';

/// Single collapsible process drawer for the assistant's reasoning pipeline.
///
/// Two rendering modes:
///   1. New: consumes [flowEvents] (list of [ExplainableFlowEvent]) — tree-
///      structured, deduped, user-language phases.
///   2. Legacy: consumes [processState] (AssistantProcessState) — flat lines
///      and content blocks.
///
/// When [flowEvents] is non-empty, the legacy [processState] is ignored.
class AssistantProcessDrawer extends StatefulWidget {
  const AssistantProcessDrawer({
    super.key,
    required this.processState,
    required this.isRunning,
    this.initiallyExpanded = false,
    this.onReferenceUrlTap,
    this.flowEvents = const <ExplainableFlowEvent>[],
    this.streamingThinkingText = '',
  });

  final AssistantProcessState processState;
  final bool isRunning;
  final bool initiallyExpanded;
  final void Function(String url)? onReferenceUrlTap;
  final List<ExplainableFlowEvent> flowEvents;
  final String streamingThinkingText;

  @override
  State<AssistantProcessDrawer> createState() => _AssistantProcessDrawerState();
}

class _AssistantProcessDrawerState extends State<AssistantProcessDrawer> {
  bool _expanded = false;
  final Set<int> _expandedBlockIndices = <int>{};

  ProcessStage? _prevStage;
  int _prevFlowEventCount = 0;

  bool get _useFlowEvents => widget.flowEvents.isNotEmpty;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  @override
  void didUpdateWidget(covariant AssistantProcessDrawer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_useFlowEvents) {
      final hasNewContent =
          widget.streamingThinkingText.length >
              oldWidget.streamingThinkingText.length ||
          widget.flowEvents.length > _prevFlowEventCount;
      if (widget.isRunning && hasNewContent && !_expanded) {
        setState(() => _expanded = true);
      }
      _prevFlowEventCount = widget.flowEvents.length;
    } else {
      if (widget.isRunning &&
          _prevStage != widget.processState.stage &&
          widget.processState.stage != ProcessStage.understanding &&
          !_expanded) {
        setState(() => _expanded = true);
      }
      _prevStage = widget.processState.stage;
    }
  }

  @override
  void dispose() => super.dispose();

  bool get _hasContentBlocks => widget.processState.contentBlocks.isNotEmpty;

  bool get _isInitialWait {
    if (_useFlowEvents) {
      return widget.flowEvents.isEmpty && widget.streamingThinkingText.isEmpty;
    }
    return widget.processState.stage == ProcessStage.understanding &&
        !_hasContentBlocks &&
        widget.processState.processLines.isEmpty;
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
            _useFlowEvents
                ? _buildFlowEventsBody(
                    textColor: textColor,
                    secondaryTextColor: secondaryTextColor,
                    accentColor: accentColor,
                  )
                : _buildBody(
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
    final headerLabel = _shortHeaderLabel();
    final monochrome = Color.lerp(secondaryTextColor, accentColor, 0.22)!;
    return GestureDetector(
      onTap: () => setState(() => _expanded = !_expanded),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupSm,
        ),
        child: Row(
          children: [
            if (!widget.isRunning)
              Padding(
                padding: EdgeInsets.only(right: AppSpacing.xs),
                child: Icon(
                  CupertinoIcons.checkmark_circle_fill,
                  size: AppTypography.base,
                  color: accentColor,
                ),
              ),
            if (widget.isRunning && _isInitialWait)
              Padding(
                padding: EdgeInsets.only(right: AppSpacing.xs + AppSpacing.xs / 2),
                child: _BreathingCapsule(color: monochrome),
              ),
            Text(
              headerLabel,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w500,
                color: textColor,
                height: AppTypography.bodyLineHeight,
              ),
            ),
            if (widget.isRunning && !_isInitialWait)
              Padding(
                padding: EdgeInsets.only(left: AppSpacing.xs),
                child: _ThreeDotPulse(color: monochrome, size: AppSpacing.xs),
              ),
            const Spacer(),
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

  String _shortHeaderLabel() {
    if (_useFlowEvents) {
      return _flowEventsHeaderLabel();
    }
    final stage = widget.processState.stage;
    if (!widget.isRunning) {
      final label = widget.processState.stageLabel;
      if (label.length <= 12) return label;
      return '${label.substring(0, AppSpacing.ten.toInt())}\u2026';
    }
    switch (stage) {
      case ProcessStage.understanding:
        return UITextConstants.assistantProcessThinking;
      case ProcessStage.searching:
        return UITextConstants.assistantProcessSearching;
      case ProcessStage.analyzing:
        return UITextConstants.assistantProcessOrganizing;
      case ProcessStage.answering:
        return UITextConstants.assistantProcessAnswering;
      case ProcessStage.completed:
        return UITextConstants.assistantProcessCompleted;
    }
  }

  String _flowEventsHeaderLabel() {
    final events = widget.flowEvents;
    if (events.isEmpty && widget.streamingThinkingText.isEmpty) {
      return UITextConstants.assistantProcessThinking;
    }
    if (!widget.isRunning) {
      final elapsed = widget.processState.elapsedMs;
      if (elapsed > 0) {
        final seconds = (elapsed / 1000).toStringAsFixed(1);
        return '已完成深度思考（用时$seconds秒）';
      }
      return UITextConstants.assistantProcessCompleted;
    }
    if (events.isEmpty) {
      return UITextConstants.assistantProcessThinking;
    }
    final activeEvent = events.lastWhere(
      (e) => e.phaseStatus == ExplainablePhaseStatus.active,
      orElse: () => events.last,
    );
    return _phaseIdToLabel(activeEvent.phaseId);
  }

  static String _phaseIdToLabel(String phaseId) {
    switch (phaseId) {
      case PhaseId.understand:
      case PhaseId.classify:
        return UITextConstants.assistantProcessThinking;
      case PhaseId.plan:
        return UITextConstants.assistantProcessThinking;
      case PhaseId.execute:
      case PhaseId.subExecute:
        return UITextConstants.assistantProcessSearching;
      case PhaseId.aggregate:
      case PhaseId.merge:
        return UITextConstants.assistantProcessOrganizing;
      case PhaseId.answer:
        return UITextConstants.assistantProcessAnswering;
      default:
        return UITextConstants.assistantProcessThinking;
    }
  }

  Widget _buildFlowEventsBody({
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    final text = widget.streamingThinkingText;
    if (text.isEmpty) return const SizedBox.shrink();

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
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            alignment: Alignment.topLeft,
            child: Text(
              text,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: secondaryTextColor,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ),
          if (widget.isRunning)
            Padding(
              padding: EdgeInsets.only(top: AppSpacing.xs / 2),
              child: _ThreeDotPulse(
                color: accentColor.withValues(alpha: 0.5),
                size: AppSpacing.xs,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildBody({
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    if (_hasContentBlocks) {
      return _buildStructuredBody(
        textColor: textColor,
        secondaryTextColor: secondaryTextColor,
        accentColor: accentColor,
      );
    }
    return _buildLegacyBody(secondaryTextColor: secondaryTextColor);
  }

  Widget _buildStructuredBody({
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    final blocks = widget.processState.contentBlocks;
    if (blocks.isEmpty) return const SizedBox.shrink();
    final detailLabel = widget.processState.stageLabel;
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
          if (detailLabel.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(
                detailLabel,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: secondaryTextColor,
                  height: AppTypography.lineHeightRelaxed,
                ),
              ),
            ),
          for (var i = 0; i < blocks.length; i++)
            _buildContentBlock(
              index: i,
              block: blocks[i],
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
              accentColor: accentColor,
            ),
          if (!widget.processState.isStreaming)
            _buildUsageStatsLine(secondaryTextColor: secondaryTextColor),
        ],
      ),
    );
  }

  Widget _buildContentBlock({
    required int index,
    required ProcessContentBlock block,
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    switch (block.type) {
      case ProcessContentBlockType.searchSummary:
        return _buildCollapsibleRefBlock(
          index: index,
          icon: CupertinoIcons.search,
          label: block.text,
          references: block.references,
          textColor: textColor,
          secondaryTextColor: secondaryTextColor,
          accentColor: accentColor,
        );
      case ProcessContentBlockType.analysisSummary:
        return _buildCollapsibleRefBlock(
          index: index,
          icon: CupertinoIcons.doc_text,
          label: block.text,
          references: block.references,
          textColor: textColor,
          secondaryTextColor: secondaryTextColor,
          accentColor: accentColor,
        );
      case ProcessContentBlockType.text:
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.three),
          child: Text(
            block.text,
            style: TextStyle(
              fontSize: AppTypography.base,
              color: secondaryTextColor,
              height: AppTypography.lineHeightRelaxed,
            ),
          ),
        );
    }
  }

  Widget _buildCollapsibleRefBlock({
    required int index,
    required IconData icon,
    required String label,
    required List<ProcessReference> references,
    required Color textColor,
    required Color secondaryTextColor,
    required Color accentColor,
  }) {
    final isBlockExpanded = _expandedBlockIndices.contains(index);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              setState(() {
                if (isBlockExpanded) {
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
                      label,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w500,
                        color: textColor,
                      ),
                    ),
                  ),
                  Icon(
                    isBlockExpanded
                        ? CupertinoIcons.chevron_up
                        : CupertinoIcons.chevron_down,
                    size: AppTypography.xsPlus,
                    color: secondaryTextColor,
                  ),
                ],
              ),
            ),
          ),
          if (isBlockExpanded && references.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(left: AppTypography.smPlus + AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: references
                    .map((ref) {
                      return GestureDetector(
                        onTap: ref.url.isNotEmpty
                            ? () => widget.onReferenceUrlTap?.call(ref.url)
                            : null,
                        child: Padding(
                          padding: EdgeInsets.only(bottom: AppSpacing.xs / 2),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  ref.title,
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
                              if (ref.url.isNotEmpty)
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
                      );
                    })
                    .toList(growable: false),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildLegacyBody({required Color secondaryTextColor}) {
    final lines = widget.processState.processLines;
    final detailLabel = widget.processState.stageLabel;
    if (lines.isEmpty && detailLabel.isEmpty) return const SizedBox.shrink();
    final isStreaming = widget.processState.isStreaming;
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
          if (detailLabel.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(
                detailLabel,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: secondaryTextColor,
                  height: AppTypography.lineHeightRelaxed,
                ),
              ),
            ),
          for (var i = 0; i < lines.length; i++)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.xs / 2),
              child: AnimatedOpacity(
                opacity: (isStreaming && i == lines.length - 1) ? 0.7 : 1.0,
                duration: const Duration(milliseconds: 300),
                child: Text(
                  lines[i],
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: secondaryTextColor,
                    height: AppTypography.lineHeightRelaxed,
                  ),
                ),
              ),
            ),
          if (!isStreaming)
            _buildUsageStatsLine(secondaryTextColor: secondaryTextColor),
        ],
      ),
    );
  }

  Widget _buildUsageStatsLine({required Color secondaryTextColor}) {
    final stats = widget.processState.usageStats;
    final elapsed = widget.processState.elapsedMs;
    final runModelCalls =
        ((stats['runModelCallCount'] as num?)?.toInt() ??
            (stats['modelCallCount'] as num?)?.toInt() ??
            0);
    final runTotalTokens =
        ((stats['runTotalTokens'] as num?)?.toInt() ??
            (stats['totalTokens'] as num?)?.toInt() ??
            0);
    final modelCalls =
        ((stats['cumulativeModelCallCount'] as num?)?.toInt() ?? runModelCalls);
    final totalTokens =
        ((stats['cumulativeTotalTokens'] as num?)?.toInt() ?? runTotalTokens);
    if (modelCalls == 0 && totalTokens == 0 && elapsed == 0) {
      return const SizedBox.shrink();
    }
    final parts = <String>[];
    if (modelCalls > 0) {
      parts.add(
        UITextConstants.assistantProcessModelCallCountTemplate.replaceFirst(
          '%s',
          '$modelCalls',
        ),
      );
      if (runModelCalls > 0 && runModelCalls != modelCalls) {
        parts.add('本轮 $runModelCalls');
      }
    }
    if (totalTokens > 0) {
      parts.add(
        UITextConstants.assistantProcessTokensTemplate.replaceFirst(
          '%s',
          '$totalTokens',
        ),
      );
      if (runTotalTokens > 0 && runTotalTokens != totalTokens) {
        parts.add('本轮Token $runTotalTokens');
      }
    }
    if (elapsed > 0) {
      final seconds = (elapsed / 1000).toStringAsFixed(1);
      parts.add(
        UITextConstants.assistantProcessElapsedTemplate.replaceFirst(
          '%s',
          seconds,
        ),
      );
    }
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.xs),
      child: Text(
        parts.join('  ·  '),
        style: TextStyle(
          fontSize: AppTypography.xs,
          color: secondaryTextColor.withValues(alpha: 0.6),
          height: AppTypography.bodyLineHeight,
        ),
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
      child: SlideTransition(
        position: _slide,
        child: widget.child,
      ),
    );
  }
}
