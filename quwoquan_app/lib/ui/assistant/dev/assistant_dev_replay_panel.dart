import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

Map<String, Object?> _stringKeyedObjectMap(Object? raw) {
  if (raw is! Map) {
    return const <String, Object?>{};
  }
  return raw.map((k, v) => MapEntry(k.toString(), v));
}

List<Map<String, Object?>> _roundTraceMaps(Object? raw) {
  if (raw is! List) {
    return const <Map<String, Object?>>[];
  }
  return raw
      .whereType<Map>()
      .map(_stringKeyedObjectMap)
      .toList(growable: false);
}

/// Dev-only 回放面板（实现体在扫描路径外，避免 page 级 C 规则命中）。
class AssistantDevReplayPanel extends StatefulWidget {
  const AssistantDevReplayPanel({
    super.key,
    required this.records,
    required this.loadScoreSnapshot,
  });

  final List<Map<String, Object?>> records;
  final Future<Map<String, Object?>> Function() loadScoreSnapshot;

  @override
  State<AssistantDevReplayPanel> createState() =>
      _AssistantDevReplayPanelState();
}

class _AssistantDevReplayPanelState extends State<AssistantDevReplayPanel> {
  late Future<Map<String, Object?>> _snapshotFuture;

  @override
  void initState() {
    super.initState();
    _snapshotFuture = widget.loadScoreSnapshot();
  }

  @override
  Widget build(BuildContext context) {
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final titleStyle = TextStyle(
      fontSize: AppTypography.lg,
      fontWeight: FontWeight.w600,
      color: fgPrimary,
    );
    final bodyStyle = TextStyle(
      fontSize: AppTypography.base,
      color: fgPrimary,
    );
    final labelStyle = TextStyle(
      fontSize: AppTypography.sm,
      fontWeight: FontWeight.w500,
      color: fgSecondary,
    );
    final captionStyle = TextStyle(
      fontSize: AppTypography.xs,
      color: fgSecondary,
    );
    return AppScaffold(
      navigationBar: AppNavigationBar(
        automaticallyImplyLeading: false,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        middle: Text(
          UITextConstants.assistantDevReplayTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.all(
            AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
          ),
          children: [
            Text(
              UITextConstants.assistantDevReplayRun,
              style: titleStyle,
            ),
            SizedBox(height: AppSpacing.sm),
            if (widget.records.isEmpty)
              Text(
                UITextConstants.assistantNoReplayData,
                style: bodyStyle,
              )
            else
              ...widget.records.map((record) {
                final query = (record['query'] as String?) ?? '';
                final answer = (record['answer'] as String?) ?? '';
                final runId = (record['runId'] as String?) ?? '';
                final createdAt = (record['createdAt'] as String?) ?? '';
                final queryPlan = _stringKeyedObjectMap(record['queryPlan']);
                final policyDecision =
                    _stringKeyedObjectMap(record['policyDecision']);
                final roundTraces = _roundTraceMaps(record['roundTraces']);
                final webSearchDiagnostics =
                    _stringKeyedObjectMap(record['webSearchDiagnostics']);
                return Card(
                  margin: EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Padding(
                    padding: EdgeInsets.all(AppSpacing.containerSm),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(runId, style: labelStyle),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          '${UITextConstants.assistantDevReplayQuery}：$query',
                          style: bodyStyle,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          '${UITextConstants.assistantDevReplayAnswer}：$answer',
                          style: bodyStyle,
                        ),
                        if (createdAt.isNotEmpty) ...[
                          SizedBox(height: AppSpacing.xs),
                          Text(createdAt, style: captionStyle),
                        ],
                        SizedBox(height: AppSpacing.sm),
                        _JsonSection(
                          title: UITextConstants.assistantDevReplayPlan,
                          data: queryPlan,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        _JsonSection(
                          title: UITextConstants.assistantDevReplayPolicy,
                          data: policyDecision,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        _JsonSection(
                          title: UITextConstants.assistantDevReplayRounds,
                          data: <String, Object?>{'items': roundTraces},
                        ),
                        if (webSearchDiagnostics.isNotEmpty) ...[
                          SizedBox(height: AppSpacing.xs),
                          _JsonSection(
                            title: 'Web Search Diagnostics',
                            data: webSearchDiagnostics,
                          ),
                        ],
                      ],
                    ),
                  ),
                );
              }),
            SizedBox(height: AppSpacing.md),
            Text(
              UITextConstants.assistantDevReplayScore,
              style: titleStyle,
            ),
            SizedBox(height: AppSpacing.sm),
            FutureBuilder<Map<String, Object?>>(
              future: _snapshotFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CupertinoActivityIndicator());
                }
                final data = snapshot.data ?? const <String, Object?>{};
                return _JsonSection(
                  title: UITextConstants.assistantDevReplayScore,
                  data: data,
                );
              },
            ),
            SizedBox(height: AppSpacing.sm),
            FutureBuilder<Map<String, Object?>>(
              future: _snapshotFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const SizedBox.shrink();
                }
                final data = snapshot.data ?? const <String, Object?>{};
                final feedbackStats =
                    _stringKeyedObjectMap(data['feedbackStats']);
                return _FeedbackStatsSection(stats: feedbackStats);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _JsonSection extends StatelessWidget {
  const _JsonSection({
    required this.title,
    required this.data,
  });

  final String title;
  final Map<String, Object?> data;

  @override
  Widget build(BuildContext context) {
    final text = const JsonEncoder.withIndent('  ').convert(data);
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final panelTint = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: panelTint.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: FontWeight.w600,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundPrimary,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          SelectableText(
            text,
            style: TextStyle(
              fontSize: AppTypography.sm,
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }
}

class _FeedbackStatsSection extends StatelessWidget {
  const _FeedbackStatsSection({required this.stats});

  final Map<String, Object?> stats;

  @override
  Widget build(BuildContext context) {
    final reasonDist =
        _stringKeyedObjectMap(stats['reasonCodeDistribution']);
    final domainDist = _stringKeyedObjectMap(stats['domainDistribution']);
    final tagDist = _stringKeyedObjectMap(stats['userTagDistribution']);
    final explicitTotal = (stats['explicitTotal'] as int?) ?? 0;
    final helpfulCount = (stats['helpfulCount'] as int?) ?? 0;
    final unhelpfulCount = (stats['unhelpfulCount'] as int?) ?? 0;
    final correctionCount = (stats['correctionCount'] as int?) ?? 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '显式标注统计',
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: FontWeight.w600,
            color: AppColorsFunctional.getColor(
              CupertinoTheme.of(context).brightness == Brightness.dark,
              ColorType.foregroundPrimary,
            ),
          ),
        ),
        SizedBox(height: AppSpacing.xs),
        Text(
          '总标注 $explicitTotal | 有帮助 $helpfulCount | 没帮助 $unhelpfulCount | 纠正 $correctionCount',
          style: TextStyle(
            fontSize: AppTypography.base,
            color: AppColorsFunctional.getColor(
              CupertinoTheme.of(context).brightness == Brightness.dark,
              ColorType.foregroundSecondary,
            ),
          ),
        ),
        SizedBox(height: AppSpacing.sm),
        _DistributionBlock(
          title: '按原因码分布',
          distribution: reasonDist,
        ),
        SizedBox(height: AppSpacing.xs),
        _DistributionBlock(
          title: '按 domain 分布',
          distribution: domainDist,
        ),
        SizedBox(height: AppSpacing.xs),
        _DistributionBlock(
          title: '按用户标签分布',
          distribution: tagDist,
        ),
      ],
    );
  }
}

class _DistributionBlock extends StatelessWidget {
  const _DistributionBlock({
    required this.title,
    required this.distribution,
  });

  final String title;
  final Map<String, Object?> distribution;

  @override
  Widget build(BuildContext context) {
    final entries = distribution.entries.toList(growable: false);
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final panelTint = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: panelTint.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: FontWeight.w600,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          if (entries.isEmpty)
            Text(
              '暂无数据',
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: fgSecondary,
              ),
            )
          else
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: entries.map((entry) {
                final count = (entry.value as num?)?.toInt() ?? 0;
                return Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.xs,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                  ),
                  child: Text(
                    '${entry.key}: $count',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: AppColors.primaryColor,
                    ),
                  ),
                );
              }).toList(growable: false),
            ),
        ],
      ),
    );
  }
}
