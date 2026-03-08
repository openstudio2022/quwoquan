import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';

/// Single collapsible process drawer for the assistant's reasoning pipeline.
///
/// Displays the four-phase reasoning process:
///   Phase 1 – understanding (waiting for model, twin-bar opposite-rotation animation)
///   Phase 2 – searching (tool calls, three-dot animation)
///   Phase 3 – analyzing (evidence synthesis, three-dot animation)
///   Phase 4 – answering (generation / judgment loop, three-dot animation)
///
/// Each phase shows structured [ProcessContentBlock]s including collapsible
/// reference lists for search/analysis results.
class AssistantProcessDrawer extends StatefulWidget {
  const AssistantProcessDrawer({
    super.key,
    required this.processState,
    required this.isRunning,
    this.initiallyExpanded = false,
    this.onReferenceUrlTap,
  });

  final AssistantProcessState processState;
  final bool isRunning;
  final bool initiallyExpanded;
  final void Function(String url)? onReferenceUrlTap;

  @override
  State<AssistantProcessDrawer> createState() => _AssistantProcessDrawerState();
}

class _AssistantProcessDrawerState extends State<AssistantProcessDrawer>
    with TickerProviderStateMixin {
  bool _expanded = false;
  late final AnimationController _twinBarController;
  final Set<int> _expandedBlockIndices = <int>{};

  // Track previous stage to auto-expand when a new phase starts
  ProcessStage? _prevStage;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
    _twinBarController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );
    if (widget.isRunning) _twinBarController.repeat();
  }

  @override
  void didUpdateWidget(covariant AssistantProcessDrawer oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Manage twin-bar animation lifecycle
    if (widget.isRunning && !_twinBarController.isAnimating) {
      _twinBarController.repeat();
    } else if (!widget.isRunning && _twinBarController.isAnimating) {
      _twinBarController.stop();
    }
    // Auto-expand when a new search/analysis phase starts during a run
    if (widget.isRunning &&
        _prevStage != widget.processState.stage &&
        widget.processState.stage != ProcessStage.understanding &&
        !_expanded) {
      setState(() => _expanded = true);
    }
    _prevStage = widget.processState.stage;
  }

  @override
  void dispose() {
    _twinBarController.dispose();
    super.dispose();
  }

  bool get _hasContentBlocks =>
      widget.processState.contentBlocks.isNotEmpty;

  bool get _isInitialWait =>
      widget.processState.stage == ProcessStage.understanding &&
      !_hasContentBlocks &&
      widget.processState.processLines.isEmpty;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final bgColor = isDark
        ? const Color(0xFF1C1C1E)
        : const Color(0xFFF5F5F7);
    final borderColor = isDark
        ? const Color(0xFF38383A)
        : const Color(0xFFE5E5EA);
    final textColor = isDark
        ? const Color(0xFFEBEBF5)
        : const Color(0xFF3A3A3C);
    final secondaryTextColor = isDark
        ? const Color(0xFF98989F)
        : const Color(0xFF8E8E93);
    final accentColor = isDark
        ? const Color(0xFF64D2FF)
        : const Color(0xFF007AFF);

    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.xs),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: borderColor, width: 0.5),
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
    return GestureDetector(
      onTap: () => setState(() => _expanded = !_expanded),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupSm,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Row(
                    children: [
                      Flexible(
                        child: Text(
                          widget.processState.stageLabel,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            fontWeight: FontWeight.w500,
                            color: textColor,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Padding(
                        padding: EdgeInsets.only(left: AppSpacing.xs),
                        child: SizedBox(
                          width: 20,
                          height: 20,
                          child: Center(
                            child: _buildStatusIndicator(accentColor, secondaryTextColor),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                // Phase progress indicator (4 steps)
                if (widget.isRunning || widget.processState.stage == ProcessStage.completed)
                  Padding(
                    padding: EdgeInsets.only(right: AppSpacing.xs),
                    child: _PhaseStepRow(
                      stage: widget.processState.stage,
                      activeColor: accentColor,
                      inactiveColor: secondaryTextColor.withValues(alpha: 0.3),
                    ),
                  ),
                Icon(
                  _expanded
                      ? CupertinoIcons.chevron_up
                      : CupertinoIcons.chevron_down,
                  size: 13,
                  color: secondaryTextColor,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Status indicator shown after the stage label:
  /// - Completed: Checkmark icon
  /// - Phase 1 (initial wait, no content): Twin rotating bars
  /// - Phase 2+ while running: Three-dot pulse
  Widget _buildStatusIndicator(Color accentColor, Color secondaryTextColor) {
    if (!widget.isRunning) {
      return Icon(
        CupertinoIcons.checkmark_circle_fill,
        size: 16,
        color: accentColor,
      );
    }
    if (_isInitialWait) {
      return _TwinBarAnimation(
        controller: _twinBarController,
        color: accentColor,
      );
    }
    // For active phases, show a compact three-dot indicator
    return _ThreeDotPulse(color: accentColor, size: 4);
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
            height: 0.5,
            color: secondaryTextColor.withValues(alpha: 0.15),
          ),
          SizedBox(height: AppSpacing.xs),
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
          padding: const EdgeInsets.only(bottom: 3),
          child: Text(
            block.text,
            style: TextStyle(
              fontSize: AppTypography.base,
              color: secondaryTextColor,
              height: 1.5,
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
                  Icon(icon, size: 13, color: accentColor),
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
                    size: 11,
                    color: secondaryTextColor,
                  ),
                ],
              ),
            ),
          ),
          if (isBlockExpanded && references.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(left: 13 + AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: references.map((ref) {
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
                                decorationColor: accentColor.withValues(alpha: 0.4),
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
                                size: 10,
                                color: accentColor.withValues(alpha: 0.6),
                              ),
                            ),
                        ],
                      ),
                    ),
                  );
                }).toList(growable: false),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildLegacyBody({required Color secondaryTextColor}) {
    final lines = widget.processState.processLines;
    if (lines.isEmpty) return const SizedBox.shrink();
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
            height: 0.5,
            color: secondaryTextColor.withValues(alpha: 0.15),
          ),
          SizedBox(height: AppSpacing.xs),
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Text(
                line,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: secondaryTextColor,
                  height: 1.5,
                ),
              ),
            ),
          if (!widget.processState.isStreaming)
            _buildUsageStatsLine(secondaryTextColor: secondaryTextColor),
        ],
      ),
    );
  }

  Widget _buildUsageStatsLine({required Color secondaryTextColor}) {
    final stats = widget.processState.usageStats;
    final elapsed = widget.processState.elapsedMs;
    final modelCalls = (stats['modelCallCount'] as num?)?.toInt() ?? 0;
    final totalTokens = (stats['totalTokens'] as num?)?.toInt() ?? 0;
    if (modelCalls == 0 && totalTokens == 0 && elapsed == 0) {
      return const SizedBox.shrink();
    }
    final parts = <String>[];
    if (modelCalls > 0) parts.add('模型调用 $modelCalls 次');
    if (totalTokens > 0) parts.add('$totalTokens tokens');
    if (elapsed > 0) {
      final seconds = (elapsed / 1000).toStringAsFixed(1);
      parts.add('耗时 ${seconds}s');
    }
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.xs),
      child: Text(
        parts.join('  ·  '),
        style: TextStyle(
          fontSize: AppTypography.xs,
          color: secondaryTextColor.withValues(alpha: 0.6),
          height: 1.4,
        ),
      ),
    );
  }
}

/// Phase 1 animation: two short rectangular bars rotating in opposite directions.
/// The left bar rotates clockwise, the right bar counter-clockwise.
/// This creates a symmetric "thinking" visual cue for the initial wait state.
class _TwinBarAnimation extends StatelessWidget {
  const _TwinBarAnimation({
    required this.controller,
    required this.color,
  });

  final AnimationController controller;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, child) {
        final angle = controller.value * 2 * math.pi;
        return Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Transform.rotate(
              angle: angle,
              child: _bar(color),
            ),
            const SizedBox(width: 3),
            Transform.rotate(
              angle: -angle,
              child: _bar(color),
            ),
          ],
        );
      },
    );
  }

  Widget _bar(Color color) {
    return Container(
      width: 7,
      height: 3,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(1.5),
      ),
    );
  }
}

/// Four-step phase progress indicator shown in the drawer header.
/// Each step is a small circle dot; completed/current steps are filled.
class _PhaseStepRow extends StatelessWidget {
  const _PhaseStepRow({
    required this.stage,
    required this.activeColor,
    required this.inactiveColor,
  });

  final ProcessStage stage;
  final Color activeColor;
  final Color inactiveColor;

  static const List<ProcessStage> _order = [
    ProcessStage.understanding,
    ProcessStage.searching,
    ProcessStage.analyzing,
    ProcessStage.answering,
  ];

  @override
  Widget build(BuildContext context) {
    final currentIdx = _stageIndex(stage);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(_order.length, (i) {
        final isActive = i <= currentIdx;
        final isCurrent = i == currentIdx && stage != ProcessStage.completed;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 1.5),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
            width: isCurrent ? 6 : 4,
            height: 4,
            decoration: BoxDecoration(
              color: isActive ? activeColor : inactiveColor,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        );
      }),
    );
  }

  int _stageIndex(ProcessStage s) {
    switch (s) {
      case ProcessStage.understanding:
        return 0;
      case ProcessStage.searching:
        return 1;
      case ProcessStage.analyzing:
        return 2;
      case ProcessStage.answering:
        return 3;
      case ProcessStage.completed:
        return 3;
    }
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
            final t = (_controller.value - delay).clamp(0.0, 1.0);
            final opacity =
                t < 0.5 ? 0.25 + 0.75 * (t * 2) : 0.25 + 0.75 * (1 - (t - 0.5) * 2);
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 1),
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
            );
          }),
        );
      },
    );
  }
}
