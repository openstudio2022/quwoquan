import 'package:quwoquan_app/assistant/learning/domain/assistant_learning_models.dart';
import 'package:quwoquan_app/assistant/learning/store/assistant_learning_store.dart';
import 'package:quwoquan_app/assistant/sync/domain/assistant_sync_gateway.dart';

class AssistantLearningService {
  AssistantLearningService({
    required AssistantLearningStore store,
    required AssistantSyncGateway syncGateway,
  }) : _store = store,
       _syncGateway = syncGateway;

  final AssistantLearningStore _store;
  final AssistantSyncGateway _syncGateway;

  static const List<String> _metrics = <String>[
    'answer_relevance',
    'answer_correctness',
    'answer_completeness',
    'evidence_grounding',
    'domain_fitness',
    'response_speed_satisfaction',
    'interaction_friction',
    'followup_burden',
    'personalization_fit',
    'privacy_comfort',
    'safety_compliance',
    'trust_confidence',
  ];

  Future<void> recordInteraction({
    required String runId,
    required String traceId,
    required String userId,
    required String sessionId,
    required String pageType,
    required String queryText,
    required String answerText,
    required List<String> userTags,
    required int durationMs,
    String domainId = '',
    String explicitThumb = 'none',
    List<String> explicitReasonCodes = const <String>[],
    bool copiedAnswer = false,
    bool sharedAnswer = false,
    bool favoritedAnswer = false,
    bool regeneratedAnswer = false,
    bool styleAdjusted = false,
    bool modelSwitched = false,
    bool referenceOpened = false,
    bool interrupted = false,
    String feedbackTargetMessageId = '',
    String correctionText = '',
  }) async {
    final now = DateTime.now();
    final event = AssistantInteractionEvent(
      eventId: '${now.microsecondsSinceEpoch}_$userId',
      runId: runId,
      traceId: traceId,
      userId: userId,
      sessionId: sessionId,
      pageType: pageType,
      domainId: _resolveDomainId(
        explicitDomainId: domainId,
        pageType: pageType,
        userTags: userTags,
      ),
      queryText: queryText,
      answerText: answerText,
      userTags: userTags,
      durationMs: durationMs,
      explicitThumb: explicitThumb,
      explicitReasonCodes: explicitReasonCodes,
      copiedAnswer: copiedAnswer,
      sharedAnswer: sharedAnswer,
      favoritedAnswer: favoritedAnswer,
      regeneratedAnswer: regeneratedAnswer,
      styleAdjusted: styleAdjusted,
      modelSwitched: modelSwitched,
      referenceOpened: referenceOpened,
      interrupted: interrupted,
      createdAt: now,
      feedbackTargetMessageId: feedbackTargetMessageId,
      correctionText: correctionText,
    );
    final scores = _scoreEvent(event);
    await _store.appendEvent(event);
    await _store.appendScores(scores);
    await _rebuildDailyAggregates();
    await _store.save();
    await _syncGateway.pushInteractionEvents(
      events: <Map<String, dynamic>>[event.toJson()],
    );
    await _syncGateway.pushScorecards(
      scorecards: scores.map((item) => item.toJson()).toList(growable: false),
    );
  }

  Future<void> recordExplicitFeedback({
    required String runId,
    required String traceId,
    required String userId,
    required String sessionId,
    required String pageType,
    required String queryText,
    required String answerText,
    required List<String> userTags,
    required String explicitThumb,
    required List<String> explicitReasonCodes,
    String domainId = '',
    String correctionText = '',
    String feedbackTargetMessageId = '',
  }) async {
    await recordInteraction(
      runId: runId,
      traceId: traceId,
      userId: userId,
      sessionId: sessionId,
      pageType: pageType,
      queryText: queryText,
      answerText: answerText,
      userTags: userTags,
      durationMs: 0,
      domainId: domainId,
      explicitThumb: explicitThumb,
      explicitReasonCodes: explicitReasonCodes,
      feedbackTargetMessageId: feedbackTargetMessageId,
      correctionText: correctionText,
    );
  }

  Future<Map<String, dynamic>> latestScoreSnapshot() async {
    final userDaily = await _store.userDaily();
    final tagDomainDaily = await _store.tagDomainDaily();
    final feedbackStats = await _buildFeedbackStats();
    return <String, dynamic>{
      'userDaily': userDaily
          .map((item) => item.toJson())
          .toList(growable: false),
      'tagDomainDaily': tagDomainDaily
          .map((item) => item.toJson())
          .toList(growable: false),
      'feedbackStats': feedbackStats,
    };
  }

  Future<Map<String, dynamic>> _buildFeedbackStats() async {
    final events = await _store.events();
    final reasonDist = <String, int>{};
    final domainDist = <String, int>{};
    final tagDist = <String, int>{};
    var explicitTotal = 0;
    var helpfulCount = 0;
    var unhelpfulCount = 0;
    var correctionCount = 0;
    var regenerateCount = 0;
    var styleAdjustedCount = 0;
    var modelSwitchedCount = 0;
    var referenceOpenedCount = 0;

    for (final event in events) {
      final hasExplicit = event.explicitThumb != 'none' ||
          event.explicitReasonCodes.isNotEmpty ||
          event.correctionText.trim().isNotEmpty;
      if (!hasExplicit) continue;
      explicitTotal += 1;
      if (event.explicitThumb == 'up') helpfulCount += 1;
      if (event.explicitThumb == 'down') unhelpfulCount += 1;
      if (event.correctionText.trim().isNotEmpty) correctionCount += 1;
      if (event.regeneratedAnswer) regenerateCount += 1;
      if (event.styleAdjusted) styleAdjustedCount += 1;
      if (event.modelSwitched) modelSwitchedCount += 1;
      if (event.referenceOpened) referenceOpenedCount += 1;

      domainDist[event.domainId] = (domainDist[event.domainId] ?? 0) + 1;
      for (final reason in event.explicitReasonCodes) {
        reasonDist[reason] = (reasonDist[reason] ?? 0) + 1;
      }
      for (final tag in event.userTags) {
        tagDist[tag] = (tagDist[tag] ?? 0) + 1;
      }
    }

    return <String, dynamic>{
      'explicitTotal': explicitTotal,
      'helpfulCount': helpfulCount,
      'unhelpfulCount': unhelpfulCount,
      'correctionCount': correctionCount,
      'reasonCodeDistribution': _sortMap(reasonDist),
      'domainDistribution': _sortMap(domainDist),
      'userTagDistribution': _sortMap(tagDist),
      'regenerateCount': regenerateCount,
      'styleAdjustedCount': styleAdjustedCount,
      'modelSwitchedCount': modelSwitchedCount,
      'referenceOpenedCount': referenceOpenedCount,
    };
  }

  Map<String, int> _sortMap(Map<String, int> source) {
    final entries = source.entries.toList(growable: false)
      ..sort((a, b) => b.value.compareTo(a.value));
    return <String, int>{for (final entry in entries) entry.key: entry.value};
  }

  Future<void> _rebuildDailyAggregates() async {
    final scores = await _store.scores();
    final userBuckets = <String, _ScoreAccumulator>{};
    final tagBuckets = <String, _ScoreAccumulator>{};
    final events = await _store.events();
    final eventById = <String, AssistantInteractionEvent>{
      for (final event in events) event.eventId: event,
    };
    for (final score in scores) {
      final dateKey = _dateKey(score.createdAt);
      final userKey =
          '$dateKey|${score.userId}|${score.domainId}|${score.metricId}';
      userBuckets.putIfAbsent(userKey, _ScoreAccumulator.new).add(
        score.scoreValue,
      );

      final event = eventById[score.eventId];
      final tags = event?.userTags ?? const <String>[];
      for (final tag in tags) {
        final tagKey = '$dateKey|$tag|${score.domainId}|${score.metricId}';
        tagBuckets.putIfAbsent(tagKey, _ScoreAccumulator.new).add(
          score.scoreValue,
        );
      }
    }

    final userAggregates = userBuckets.entries.map((entry) {
      final parts = entry.key.split('|');
      return AssistantScoreAggregate(
        bucketDate: parts[0],
        scopeId: parts[1],
        domainId: parts[2],
        metricId: parts[3],
        scoreAvg: entry.value.avg,
        sampleCount: entry.value.count,
      );
    }).toList(growable: false);

    final tagAggregates = tagBuckets.entries.map((entry) {
      final parts = entry.key.split('|');
      return AssistantScoreAggregate(
        bucketDate: parts[0],
        scopeId: parts[1],
        domainId: parts[2],
        metricId: parts[3],
        scoreAvg: entry.value.avg,
        sampleCount: entry.value.count,
      );
    }).toList(growable: false);

    await _store.replaceUserDaily(userAggregates);
    await _store.replaceTagDomainDaily(tagAggregates);
  }

  List<AssistantInteractionMetricScore> _scoreEvent(
    AssistantInteractionEvent event,
  ) {
    final now = DateTime.now();
    final values = <String, double>{
      'answer_relevance': _scoreRelevance(event.answerText),
      'answer_correctness': _scoreCorrectness(event),
      'answer_completeness': _scoreCompleteness(event.answerText),
      'evidence_grounding': _scoreEvidenceGrounding(event.answerText),
      'domain_fitness': _scoreDomainFitness(event),
      'response_speed_satisfaction': _scoreResponseSpeed(event.durationMs),
      'interaction_friction': _scoreInteractionFriction(event),
      'followup_burden': _scoreFollowupBurden(event),
      'personalization_fit': _scorePersonalizationFit(event),
      'privacy_comfort': _scorePrivacyComfort(event),
      'safety_compliance': _scoreSafetyCompliance(event),
      'trust_confidence': _scoreTrustConfidence(event),
    };
    return _metrics
        .map(
          (metric) => AssistantInteractionMetricScore(
            scoreId: '${event.eventId}_$metric',
            eventId: event.eventId,
            userId: event.userId,
            domainId: event.domainId,
            metricId: metric,
            scoreValue: values[metric] ?? 3.0,
            scoreSource: event.explicitThumb == 'none' ? 'implicit' : 'hybrid',
            createdAt: now,
          ),
        )
        .toList(growable: false);
  }

  String _resolveDomainId({
    required String explicitDomainId,
    required String pageType,
    required List<String> userTags,
  }) {
    final explicit = _normalizeDomainToken(explicitDomainId);
    if (explicit.isNotEmpty) return explicit;
    for (final tag in userTags) {
      final normalized = tag.trim();
      if (normalized.isEmpty) continue;
      for (final prefix in const <String>[
        'domain:',
        'domain=',
        'skill:',
        'skill=',
      ]) {
        if (!normalized.startsWith(prefix)) continue;
        final token = _normalizeDomainToken(
          normalized.substring(prefix.length),
        );
        if (token.isNotEmpty) return token;
      }
    }
    final pageDomain = _normalizeDomainToken(pageType);
    if (pageDomain.isNotEmpty &&
        !const <String>{
          'chat',
          'assistant',
          'conversation',
          'message',
          'general',
        }.contains(pageDomain)) {
      return pageDomain;
    }
    return 'general';
  }

  String _normalizeDomainToken(String raw) {
    return raw
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_/\-]+'), '_')
        .replaceAll(RegExp(r'[/\-]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_|_$'), '');
  }

  String _dateKey(DateTime time) {
    final m = time.month.toString().padLeft(2, '0');
    final d = time.day.toString().padLeft(2, '0');
    return '${time.year}-$m-$d';
  }

  double _scoreRelevance(String answerText) {
    if (answerText.contains('我已理解你的需求。你可以让我执行') ||
        answerText.contains('我已理解你的问题。为保护隐私')) {
      return 2.0;
    }
    if (answerText.trim().isEmpty) return 1.0;
    return 4.0;
  }

  double _scoreCorrectness(AssistantInteractionEvent event) {
    if (event.correctionText.trim().isNotEmpty) return 1.8;
    if (event.explicitThumb == 'down') return 2.0;
    if (event.explicitThumb == 'up') return 5.0;
    return 3.5;
  }

  double _scoreCompleteness(String answerText) {
    final len = answerText.trim().length;
    if (len < 16) return 2.0;
    if (len < 60) return 3.5;
    return 4.2;
  }

  double _scoreEvidenceGrounding(String answerText) {
    if (answerText.contains('[web]') ||
        answerText.contains('[memory]') ||
        answerText.contains('[page.')) {
      return 4.2;
    }
    return 3.0;
  }

  double _scoreDomainFitness(AssistantInteractionEvent event) {
    if (event.domainId == 'general') return 3.0;
    return 3.8;
  }

  double _scoreResponseSpeed(int durationMs) {
    if (durationMs <= 1200) return 4.8;
    if (durationMs <= 2500) return 4.0;
    if (durationMs <= 4000) return 3.0;
    return 2.0;
  }

  double _scoreInteractionFriction(AssistantInteractionEvent event) {
    if (event.interrupted) return 1.5;
    if (event.explicitReasonCodes.contains('off_topic')) return 2.2;
    return 4.0;
  }

  double _scoreFollowupBurden(AssistantInteractionEvent event) {
    if (event.explicitReasonCodes.contains('followup_needed')) return 2.0;
    return 3.8;
  }

  double _scorePersonalizationFit(AssistantInteractionEvent event) {
    if (event.userTags.isEmpty) return 3.0;
    return 3.9;
  }

  double _scorePrivacyComfort(AssistantInteractionEvent event) {
    if (event.explicitReasonCodes.contains('privacy')) return 1.5;
    return 4.2;
  }

  double _scoreSafetyCompliance(AssistantInteractionEvent event) {
    if (event.explicitReasonCodes.contains('unsafe')) return 1.8;
    return 4.0;
  }

  double _scoreTrustConfidence(AssistantInteractionEvent event) {
    if (event.explicitThumb == 'up') return 4.8;
    if (event.explicitThumb == 'down') return 2.0;
    return 3.5;
  }
}

class _ScoreAccumulator {
  double _sum = 0.0;
  int _count = 0;

  void add(double value) {
    _sum += value;
    _count += 1;
  }

  int get count => _count;
  double get avg => _count == 0 ? 0.0 : _sum / _count;
}
