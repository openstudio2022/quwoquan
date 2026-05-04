import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
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
  final void Function(AssistantCitation reference)? onReferenceTap;

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

  List<String> _headerMetricTexts() {
    final metrics = <String>[];
    final acceptedCount = _viewModel.acceptedDocumentCount > 0
        ? _viewModel.acceptedDocumentCount
        : _viewModel.referenceCount;
    final searchedCount = _viewModel.searchedDocumentCount > 0
        ? _viewModel.searchedDocumentCount
        : _viewModel.processedDocumentCount;
    if (searchedCount > 0) {
      metrics.add(
        UITextConstants.assistantProcessProcessedCountTemplate.replaceFirst(
          '%s',
          searchedCount.toString(),
        ),
      );
    }
    if (acceptedCount > 0) {
      metrics.add(
        UITextConstants.assistantProcessAcceptedCountChipTemplate.replaceFirst(
          '%s',
          acceptedCount.toString(),
        ),
      );
    }
    if (_viewModel.elapsedMs >= 1000) {
      metrics.add(
        UITextConstants.assistantProcessElapsedTemplate.replaceFirst(
          '%s',
          _elapsedSeconds().toString(),
        ),
      );
    }
    return metrics;
  }

  String _headerLabel() {
    if (_viewModel.isRunning) {
      return UITextConstants.assistantProcessRunningSummary;
    }
    return UITextConstants.assistantProcessCompletedSummary;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
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
    final linkColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final surfaceTint = secondaryTextColor.withValues(
      alpha: isDark ? 0.08 : 0.03,
    );
    final bodySurfaceTint = secondaryTextColor.withValues(
      alpha: isDark ? 0.12 : 0.05,
    );
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.intraGroupLg),
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
            Container(
              key: TestKeys.assistantProcessBody,
              decoration: BoxDecoration(
                color: Color.alphaBlend(bodySurfaceTint, bgColor),
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(AppSpacing.borderRadius),
                  bottomRight: Radius.circular(AppSpacing.borderRadius),
                ),
                border: Border(
                  top: BorderSide(
                    color: borderColor.withValues(alpha: 0.9),
                    width: AppSpacing.one / 2,
                  ),
                ),
              ),
              child: _buildBody(
                textColor: textColor,
                secondaryTextColor: secondaryTextColor,
                linkColor: linkColor,
              ),
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
    final metricTexts = _headerMetricTexts();
    return GestureDetector(
      key: TestKeys.assistantProcessHeader,
      onTap: () => setState(() => _expanded = !_expanded),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupLg,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
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
                    for (final metric in metricTexts) ...[
                      SizedBox(width: AppSpacing.xs),
                      _buildHeaderMetricChip(
                        label: metric,
                        secondaryTextColor: secondaryTextColor,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            if (_viewModel.isRunning) ...[
              SizedBox(width: AppSpacing.xs),
              SizedBox(
                width: AppSpacing.iconButtonMinSizeSm - AppSpacing.xs,
                height: AppSpacing.iconButtonMinSizeSm - AppSpacing.xs,
                child: Center(child: _BreathingCapsule(color: monochrome)),
              ),
            ],
            SizedBox(width: AppSpacing.xs),
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
    required Color linkColor,
  }) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.containerSm,
        right: AppSpacing.containerSm,
        top: AppSpacing.intraGroupLg,
        bottom: AppSpacing.intraGroupLg,
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
              linkColor: linkColor,
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
    required Color linkColor,
  }) {
    if (block.kind == AssistantJourneyBlockKind.referenceStats) {
      return _buildReferenceStatsBlock(
        index: index,
        block: block,
        textColor: textColor,
        secondaryTextColor: secondaryTextColor,
        linkColor: linkColor,
      );
    }
    final bulletLines = block.items.isNotEmpty
        ? const <String>[]
        : _bulletLines(block.detail);
    final paragraphLines = _paragraphLines(block.detail);
    if (block.headline.isEmpty &&
        paragraphLines.isEmpty &&
        bulletLines.isEmpty &&
        block.items.isEmpty &&
        !block.hasReferences) {
      return const SizedBox.shrink();
    }
    final isExpanded = _expandedBlockIndices.contains(index);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (block.headline.isNotEmpty) ...[
            Text(
              block.headline,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w500,
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
                    color: textColor.withValues(alpha: 0.9),
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
                    color: textColor.withValues(alpha: 0.9),
                    height: AppTypography.lineHeightRelaxed,
                  ),
                ),
              ),
            ),
          ],
          if (block.items.isNotEmpty) ...[
            SizedBox(height: AppSpacing.one),
            ...block.items.map(
              (item) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.xs),
                child: _buildNarrativeItemRow(
                  item,
                  textColor: textColor,
                  secondaryTextColor: secondaryTextColor,
                ),
              ),
            ),
          ],
          if (block.hasReferences) ...[
            SizedBox(height: AppSpacing.one),
            _buildReferenceSummaryRow(
              index: index,
              block: block,
              textColor: textColor,
              secondaryTextColor: secondaryTextColor,
              isExpanded: isExpanded,
            ),
            if (isExpanded) ...[
              SizedBox(height: AppSpacing.one),
              ...List<Widget>.generate(block.references.length, (refIndex) {
                return Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.one),
                  child: _buildReferenceEntry(
                    reference: block.references[refIndex],
                    index: refIndex,
                    textColor: textColor,
                    linkColor: linkColor,
                  ),
                );
              }),
            ],
          ],
        ],
      ),
    );
  }

  Widget _buildHeaderMetricChip({
    required String label,
    required Color secondaryTextColor,
  }) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.one,
      ),
      decoration: BoxDecoration(
        color: secondaryTextColor.withValues(alpha: 0.06),
        border: Border.all(
          color: secondaryTextColor.withValues(alpha: 0.12),
          width: AppSpacing.one / 2,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.sm,
          fontWeight: FontWeight.w500,
          color: secondaryTextColor.withValues(alpha: 0.82),
          height: AppTypography.bodyLineHeight,
        ),
      ),
    );
  }

  Widget _buildReferenceStatsBlock({
    required int index,
    required AssistantJourneyBlockViewModel block,
    required Color textColor,
    required Color secondaryTextColor,
    required Color linkColor,
  }) {
    if (block.headline.isEmpty && !block.hasReferences) {
      return const SizedBox.shrink();
    }
    final isExpanded = _expandedBlockIndices.contains(index);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildReferenceSummaryRow(
            index: index,
            block: block,
            textColor: textColor,
            secondaryTextColor: secondaryTextColor,
            isExpanded: isExpanded,
            fallbackLabel: block.headline,
          ),
          if (isExpanded && block.hasReferences) ...[
            SizedBox(height: AppSpacing.one),
            ...List<Widget>.generate(block.references.length, (refIndex) {
              return Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.one),
                child: _buildReferenceEntry(
                  reference: block.references[refIndex],
                  index: refIndex,
                  textColor: textColor,
                  linkColor: linkColor,
                ),
              );
            }),
          ],
        ],
      ),
    );
  }

  Widget _buildReferenceSummaryRow({
    required int index,
    required AssistantJourneyBlockViewModel block,
    required Color textColor,
    required Color secondaryTextColor,
    required bool isExpanded,
    String fallbackLabel = '',
  }) {
    final label = block.referenceLabel.trim().isNotEmpty
        ? block.referenceLabel.trim()
        : (fallbackLabel.trim().isNotEmpty
              ? fallbackLabel.trim()
              : _referenceSummaryLabel(block));
    if (label.isEmpty) {
      return const SizedBox.shrink();
    }
    return GestureDetector(
      onTap: block.hasReferences
          ? () {
              setState(() {
                if (isExpanded) {
                  _expandedBlockIndices.remove(index);
                } else {
                  _expandedBlockIndices.add(index);
                }
              });
            }
          : null,
      behavior: HitTestBehavior.opaque,
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w400,
                color: textColor.withValues(alpha: 0.88),
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ),
          if (block.hasReferences)
            Icon(
              isExpanded
                  ? CupertinoIcons.chevron_up
                  : CupertinoIcons.chevron_down,
              size: AppTypography.xsPlus,
              color: secondaryTextColor.withValues(alpha: 0.72),
            ),
        ],
      ),
    );
  }

  String _referenceSummaryLabel(AssistantJourneyBlockViewModel block) {
    if (block.referenceLabel.trim().isNotEmpty) {
      return block.referenceLabel.trim();
    }
    return _referenceCountLabel(block.references.length);
  }

  Widget _buildReferenceEntry({
    required AssistantJourneyReferenceViewModel reference,
    required int index,
    required Color textColor,
    required Color linkColor,
  }) {
    final source = reference.source.trim();
    final title = reference.title.trim().isNotEmpty
        ? reference.title.trim()
        : (source.isNotEmpty ? source : '参考来源 ${index + 1}');
    final url = reference.url.trim();
    return GestureDetector(
      onTap: url.isNotEmpty
          ? () => widget.onReferenceTap?.call(
              AssistantCitation(
                url: url,
                title: reference.title,
                source: reference.source,
              ),
            )
          : null,
      behavior: HitTestBehavior.opaque,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '${index + 1}. $title',
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: FontWeight.w500,
              color: url.isNotEmpty
                  ? linkColor
                  : textColor.withValues(alpha: 0.88),
              height: AppTypography.lineHeightRelaxed,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNarrativeItemRow(
    String item, {
    required Color textColor,
    required Color secondaryTextColor,
  }) {
    final parts = _splitItemLabel(item);
    if (parts == null) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.xs, right: AppSpacing.xs),
            child: Container(
              width: AppSpacing.xs,
              height: AppSpacing.xs,
              decoration: BoxDecoration(
                color: secondaryTextColor.withValues(alpha: 0.55),
                shape: BoxShape.circle,
              ),
            ),
          ),
          Expanded(
            child: Text(
              item,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w400,
                color: textColor.withValues(alpha: 0.88),
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.one,
          ),
          decoration: BoxDecoration(
            color: secondaryTextColor.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: Text(
            parts.label,
            style: TextStyle(
              fontSize: AppTypography.sm,
              fontWeight: FontWeight.w600,
              color: secondaryTextColor.withValues(alpha: 0.92),
              height: AppTypography.bodyLineHeight,
            ),
          ),
        ),
        if (parts.body.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.one),
            child: Text(
              parts.body,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w400,
                color: textColor.withValues(alpha: 0.88),
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
          ),
      ],
    );
  }

  _NarrativeItemParts? _splitItemLabel(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final fullWidthIndex = trimmed.indexOf('：');
    final asciiIndex = trimmed.indexOf(':');
    final splitIndex = fullWidthIndex >= 0 ? fullWidthIndex : asciiIndex;
    if (splitIndex <= 0 || splitIndex >= trimmed.length - 1) {
      return null;
    }
    final label = trimmed.substring(0, splitIndex).trim();
    final body = trimmed.substring(splitIndex + 1).trim();
    if (label.isEmpty || body.isEmpty) {
      return null;
    }
    return _NarrativeItemParts(label: label, body: body);
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

class _NarrativeItemParts {
  const _NarrativeItemParts({required this.label, required this.body});

  final String label;
  final String body;
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
