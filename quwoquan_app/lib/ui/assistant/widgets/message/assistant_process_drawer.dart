import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_journey_view_model.dart';

class AssistantProcessDrawer extends StatefulWidget {
  const AssistantProcessDrawer({
    super.key,
    required this.viewModel,
    this.initiallyExpanded = false,
    this.onReferenceTap,
  });

  final AssistantJourneyViewModel viewModel;
  final bool initiallyExpanded;
  final void Function(Map<String, dynamic> reference)? onReferenceTap;

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
    return _viewModel.elapsedMs >= 6000 &&
        _viewModel.stages.isEmpty &&
        _viewModel.blocks.isEmpty;
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
    if (_viewModel.isRunning) {
      return UITextConstants.assistantProcessRunningSummary;
    }
    if (!_viewModel.isRunning && _viewModel.finalAnswerReady) {
      return _summaryHeaderLabel();
    }
    if (_viewModel.summary.isNotEmpty) {
      return _viewModel.summary;
    }
    return _summaryHeaderLabel();
  }

  String _headerSubtitle() {
    if (_isLongWaitWithoutProgress) {
      return _waitReassuranceText();
    }
    if (_viewModel.isRunning) {
      final phase = _viewModel.activeStageLabel.trim();
      if (phase.isNotEmpty) {
        return phase;
      }
    }
    return '';
  }

  @override
  Widget build(BuildContext context) {
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
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
    final surfaceTint = secondaryTextColor.withValues(
      alpha: isDark ? 0.12 : 0.04,
    );
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.sm),
      decoration: BoxDecoration(
        color: Color.alphaBlend(surfaceTint, bgColor),
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
          ),
          if (_expanded)
            _buildBody(
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
            ),
        ],
      ),
    );
  }

  Widget _buildHeader({
    required Color textColor,
    required Color secondaryTextColor,
  }) {
    final monochrome = secondaryTextColor.withValues(alpha: 0.8);
    final subtitle = _headerSubtitle();
    return GestureDetector(
      key: TestKeys.assistantProcessHeader,
      onTap: () => setState(() => _expanded = !_expanded),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Padding(
              padding: EdgeInsets.only(right: AppSpacing.sm),
              child: SizedBox(
                width: AppSpacing.iconButtonMinSizeSm - AppSpacing.xs,
                height: AppSpacing.iconButtonMinSizeSm - AppSpacing.xs,
                child: Center(
                  child: _viewModel.isRunning
                      ? _BreathingCapsule(color: monochrome)
                      : Icon(
                          CupertinoIcons.checkmark_circle_fill,
                          size: AppTypography.base + 1,
                          color: monochrome,
                        ),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _headerLabel(),
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: FontWeight.w600,
                      color: textColor,
                      height: AppTypography.bodyLineHeight,
                    ),
                  ),
                  if (subtitle.isNotEmpty)
                    Padding(
                      padding: EdgeInsets.only(top: AppSpacing.one),
                      child: Text(
                        subtitle,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: secondaryTextColor.withValues(alpha: 0.9),
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
  }) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.containerSm,
        right: AppSpacing.containerSm,
        bottom: AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _viewModel.blocks.length; i++)
            _buildBlock(
              index: i,
              block: _viewModel.blocks[i],
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
            ),
        ],
      ),
    );
  }

  Widget _buildBlock({
    required int index,
    required AssistantJourneyBlockViewModel block,
    required Color textColor,
    required Color secondaryTextColor,
  }) {
    final bulletLines = block.items.isNotEmpty
        ? block.items
        : _bulletLines(block.detail);
    final paragraphLines = _paragraphLines(block.detail);
    final isExpanded = _expandedBlockIndices.contains(index);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildStageHeading(
            label: _stageLabelFor(block.stageId),
            secondaryTextColor: secondaryTextColor,
          ),
          if (block.headline.isNotEmpty) ...[
            SizedBox(height: AppSpacing.one),
            Text(
              block.headline,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w400,
                color: textColor,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ],
          if (paragraphLines.isNotEmpty) ...[
            SizedBox(height: block.headline.isNotEmpty ? AppSpacing.one : 0),
            ...paragraphLines.map(
              (line) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.one),
                child: Text(
                  line,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w400,
                    color: textColor.withValues(alpha: 0.88),
                    height: AppTypography.lineHeightRelaxed,
                  ),
                ),
              ),
            ),
          ],
          if (bulletLines.isNotEmpty) ...[
            SizedBox(height: AppSpacing.one),
            ...bulletLines.map(
              (line) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.one),
                child: Text(
                  '• $line',
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w400,
                    color: textColor.withValues(alpha: 0.88),
                    height: AppTypography.lineHeightRelaxed,
                  ),
                ),
              ),
            ),
          ],
          if (block.hasReferences) ...[
            SizedBox(height: AppSpacing.one),
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
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _referenceSummaryLabel(block),
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w400,
                        color: textColor.withValues(alpha: 0.88),
                        height: AppTypography.lineHeightRelaxed,
                      ),
                    ),
                  ),
                  Icon(
                    isExpanded
                        ? CupertinoIcons.chevron_up
                        : CupertinoIcons.chevron_down,
                    size: AppTypography.xsPlus,
                    color: secondaryTextColor.withValues(alpha: 0.72),
                  ),
                ],
              ),
            ),
            if (isExpanded) ...[
              SizedBox(height: AppSpacing.one),
              ...List<Widget>.generate(block.references.length, (refIndex) {
                final reference = block.references[refIndex];
                final sourceSuffix = reference.source.trim().isNotEmpty
                    ? ' · ${reference.source.trim()}'
                    : '';
                return GestureDetector(
                  onTap: reference.url.isNotEmpty
                      ? () => widget.onReferenceTap?.call(<String, dynamic>{
                          'title': reference.title,
                          'url': reference.url,
                          'source': reference.source,
                        })
                      : null,
                  behavior: HitTestBehavior.opaque,
                  child: Padding(
                    padding: EdgeInsets.only(bottom: AppSpacing.one),
                    child: Text(
                      '${refIndex + 1}. ${reference.title}$sourceSuffix',
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w400,
                        color: textColor.withValues(alpha: 0.88),
                        height: AppTypography.lineHeightRelaxed,
                      ),
                    ),
                  ),
                );
              }),
            ],
          ],
        ],
      ),
    );
  }

  Widget _buildStageHeading({
    required String label,
    required Color secondaryTextColor,
  }) {
    return Text(
      label,
      style: TextStyle(
        fontSize: AppTypography.base,
        fontWeight: FontWeight.w400,
        color: secondaryTextColor.withValues(alpha: 0.82),
        height: AppTypography.bodyLineHeight,
      ),
    );
  }

  String _referenceSummaryLabel(AssistantJourneyBlockViewModel block) {
    if (block.referenceLabel.trim().isNotEmpty) {
      return block.referenceLabel.trim();
    }
    return _referenceCountLabel(block.references.length);
  }

  String _stageLabelFor(ProcessStepId stageId) {
    switch (stageId) {
      case ProcessStepId.understanding:
        return UITextConstants.assistantProcessStageUnderstand;
      case ProcessStepId.retrievalDesign:
        return UITextConstants.assistantProcessStageUnderstand;
      case ProcessStepId.retrievalProcessing:
        return UITextConstants.assistantProcessStageRetrievalProcessing;
      case ProcessStepId.answerOrganization:
        return UITextConstants.assistantProcessStageAnswer;
      case ProcessStepId.unknown:
        return UITextConstants.assistantProcessStageUnderstand;
    }
  }

  List<String> _paragraphLines(String detail) {
    return detail
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty && !line.startsWith('- '))
        .toList(growable: false);
  }

  List<String> _bulletLines(String detail) {
    return detail
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.startsWith('- '))
        .map((line) => line.substring(2).trim())
        .where((line) => line.isNotEmpty)
        .toList(growable: false);
  }
}

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
