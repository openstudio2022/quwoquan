import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class AssistantDevReplayPage extends StatefulWidget {
  const AssistantDevReplayPage({
    super.key,
    required this.records,
    required this.loadScoreSnapshot,
  });

  final List<Map<String, dynamic>> records;
  final Future<Map<String, dynamic>> Function() loadScoreSnapshot;

  @override
  State<AssistantDevReplayPage> createState() => _AssistantDevReplayPageState();
}

class _AssistantDevReplayPageState extends State<AssistantDevReplayPage> {
  late Future<Map<String, dynamic>> _snapshotFuture;

  @override
  void initState() {
    super.initState();
    _snapshotFuture = widget.loadScoreSnapshot();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          UITextConstants.assistantDevReplayTitle,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(
          AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ??
              AppSpacing.containerMd,
        ),
        children: [
          Text(
            UITextConstants.assistantDevReplayRun,
            style: theme.textTheme.titleMedium,
          ),
          SizedBox(height: AppSpacing.sm),
          if (widget.records.isEmpty)
            Text(
              UITextConstants.assistantNoReplayData,
              style: theme.textTheme.bodyMedium,
            )
          else
            ...widget.records.map((record) {
              final query = (record['query'] as String?) ?? '';
              final answer = (record['answer'] as String?) ?? '';
              final runId = (record['runId'] as String?) ?? '';
              final createdAt = (record['createdAt'] as String?) ?? '';
              final queryPlan = (record['queryPlan'] as Map?)?.cast<String, dynamic>() ??
                  const <String, dynamic>{};
              final policyDecision = (record['policyDecision'] as Map?)?.cast<String, dynamic>() ??
                  const <String, dynamic>{};
              final roundTraces = (record['roundTraces'] as List?)
                      ?.whereType<Map>()
                      .map((item) => item.cast<String, dynamic>())
                      .toList(growable: false) ??
                  const <Map<String, dynamic>>[];
              final webSearchDiagnostics =
                  (record['webSearchDiagnostics'] as Map?)
                          ?.cast<String, dynamic>() ??
                      const <String, dynamic>{};
              return Card(
                margin: EdgeInsets.only(bottom: AppSpacing.sm),
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.containerSm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(runId, style: theme.textTheme.labelMedium),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        '${UITextConstants.assistantDevReplayQuery}：$query',
                        style: theme.textTheme.bodyMedium,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        '${UITextConstants.assistantDevReplayAnswer}：$answer',
                        style: theme.textTheme.bodyMedium,
                      ),
                      if (createdAt.isNotEmpty) ...[
                        SizedBox(height: AppSpacing.xs),
                        Text(createdAt, style: theme.textTheme.labelSmall),
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
                        data: <String, dynamic>{'items': roundTraces},
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
            style: theme.textTheme.titleMedium,
          ),
          SizedBox(height: AppSpacing.sm),
          FutureBuilder<Map<String, dynamic>>(
            future: _snapshotFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              final data = snapshot.data ?? const <String, dynamic>{};
              return _JsonSection(
                title: UITextConstants.assistantDevReplayScore,
                data: data,
              );
            },
          ),
          SizedBox(height: AppSpacing.sm),
          FutureBuilder<Map<String, dynamic>>(
            future: _snapshotFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const SizedBox.shrink();
              }
              final data = snapshot.data ?? const <String, dynamic>{};
              final feedbackStats = (data['feedbackStats'] as Map?)
                      ?.cast<String, dynamic>() ??
                  const <String, dynamic>{};
              return _FeedbackStatsSection(stats: feedbackStats);
            },
          ),
        ],
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
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final text = const JsonEncoder.withIndent('  ').convert(data);
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.labelLarge),
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

  final Map<String, dynamic> stats;

  @override
  Widget build(BuildContext context) {
    final reasonDist = (stats['reasonCodeDistribution'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final domainDist =
        (stats['domainDistribution'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final tagDist =
        (stats['userTagDistribution'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final explicitTotal = (stats['explicitTotal'] as int?) ?? 0;
    final helpfulCount = (stats['helpfulCount'] as int?) ?? 0;
    final unhelpfulCount = (stats['unhelpfulCount'] as int?) ?? 0;
    final correctionCount = (stats['correctionCount'] as int?) ?? 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '显式标注统计',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        SizedBox(height: AppSpacing.xs),
        Text(
          '总标注 $explicitTotal | 有帮助 $helpfulCount | 没帮助 $unhelpfulCount | 纠正 $correctionCount',
          style: Theme.of(context).textTheme.bodyMedium,
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
  final Map<String, dynamic> distribution;

  @override
  Widget build(BuildContext context) {
    final entries = distribution.entries.toList(growable: false);
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.labelLarge),
          SizedBox(height: AppSpacing.xs),
          if (entries.isEmpty)
            Text('暂无数据', style: Theme.of(context).textTheme.bodySmall)
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

