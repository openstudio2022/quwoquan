import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/assistant/sync/assistant_sync.dart';

const String assistantStorageSubdir = '.personal_' 'assistant';

Future<String> getAssistantStoragePath(String filename) async {
  final dir = await getApplicationDocumentsDirectory();
  var basePath = dir.path;
  if (basePath.endsWith('app_flutter')) {
    basePath = Directory(basePath).parent.path;
  }
  return '$basePath/$assistantStorageSubdir/$filename';
}

class AssistantInteractionEvent {
  const AssistantInteractionEvent({
    required this.eventId,
    required this.runId,
    required this.traceId,
    required this.userId,
    required this.sessionId,
    required this.pageType,
    required this.domainId,
    required this.queryText,
    required this.answerText,
    required this.userTags,
    required this.durationMs,
    required this.explicitThumb,
    required this.explicitReasonCodes,
    required this.copiedAnswer,
    required this.sharedAnswer,
    required this.favoritedAnswer,
    required this.regeneratedAnswer,
    required this.styleAdjusted,
    required this.modelSwitched,
    required this.referenceOpened,
    required this.interrupted,
    required this.createdAt,
    this.feedbackTargetMessageId = '',
    this.correctionText = '',
  });

  final String eventId;
  final String runId;
  final String traceId;
  final String userId;
  final String sessionId;
  final String pageType;
  final String domainId;
  final String queryText;
  final String answerText;
  final List<String> userTags;
  final int durationMs;
  final String explicitThumb;
  final List<String> explicitReasonCodes;
  final bool copiedAnswer;
  final bool sharedAnswer;
  final bool favoritedAnswer;
  final bool regeneratedAnswer;
  final bool styleAdjusted;
  final bool modelSwitched;
  final bool referenceOpened;
  final bool interrupted;
  final DateTime createdAt;
  final String feedbackTargetMessageId;
  final String correctionText;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'eventId': eventId,
      'runId': runId,
      'traceId': traceId,
      'userId': userId,
      'sessionId': sessionId,
      'pageType': pageType,
      'domainId': domainId,
      'queryText': queryText,
      'answerText': answerText,
      'userTags': userTags,
      'durationMs': durationMs,
      'explicitThumb': explicitThumb,
      'explicitReasonCodes': explicitReasonCodes,
      'copiedAnswer': copiedAnswer,
      'sharedAnswer': sharedAnswer,
      'favoritedAnswer': favoritedAnswer,
      'regeneratedAnswer': regeneratedAnswer,
      'styleAdjusted': styleAdjusted,
      'modelSwitched': modelSwitched,
      'referenceOpened': referenceOpened,
      'interrupted': interrupted,
      'createdAt': createdAt.toIso8601String(),
      'feedbackTargetMessageId': feedbackTargetMessageId,
      'correctionText': correctionText,
    };
  }

  factory AssistantInteractionEvent.fromJson(Map<String, dynamic> json) {
    return AssistantInteractionEvent(
      eventId: (json['eventId'] as String?) ?? '',
      runId: (json['runId'] as String?) ?? '',
      traceId: (json['traceId'] as String?) ?? '',
      userId: (json['userId'] as String?) ?? '',
      sessionId: (json['sessionId'] as String?) ?? '',
      pageType: (json['pageType'] as String?) ?? 'chat',
      domainId: (json['domainId'] as String?) ?? 'general',
      queryText: (json['queryText'] as String?) ?? '',
      answerText: (json['answerText'] as String?) ?? '',
      userTags: (json['userTags'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      durationMs: (json['durationMs'] as int?) ?? 0,
      explicitThumb: (json['explicitThumb'] as String?) ?? 'none',
      explicitReasonCodes: (json['explicitReasonCodes'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      copiedAnswer: json['copiedAnswer'] == true,
      sharedAnswer: json['sharedAnswer'] == true,
      favoritedAnswer: json['favoritedAnswer'] == true,
      regeneratedAnswer: json['regeneratedAnswer'] == true,
      styleAdjusted: json['styleAdjusted'] == true,
      modelSwitched: json['modelSwitched'] == true,
      referenceOpened: json['referenceOpened'] == true,
      interrupted: json['interrupted'] == true,
      createdAt:
          DateTime.tryParse((json['createdAt'] as String?) ?? '') ??
          DateTime.now(),
      feedbackTargetMessageId:
          (json['feedbackTargetMessageId'] as String?) ?? '',
      correctionText: (json['correctionText'] as String?) ?? '',
    );
  }
}

class AssistantInteractionMetricScore {
  const AssistantInteractionMetricScore({
    required this.scoreId,
    required this.eventId,
    required this.userId,
    required this.domainId,
    required this.metricId,
    required this.scoreValue,
    required this.scoreSource,
    required this.createdAt,
  });

  final String scoreId;
  final String eventId;
  final String userId;
  final String domainId;
  final String metricId;
  final double scoreValue;
  final String scoreSource;
  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'scoreId': scoreId,
      'eventId': eventId,
      'userId': userId,
      'domainId': domainId,
      'metricId': metricId,
      'scoreValue': scoreValue,
      'scoreSource': scoreSource,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory AssistantInteractionMetricScore.fromJson(Map<String, dynamic> json) {
    return AssistantInteractionMetricScore(
      scoreId: (json['scoreId'] as String?) ?? '',
      eventId: (json['eventId'] as String?) ?? '',
      userId: (json['userId'] as String?) ?? '',
      domainId: (json['domainId'] as String?) ?? 'general',
      metricId: (json['metricId'] as String?) ?? '',
      scoreValue: (json['scoreValue'] as num?)?.toDouble() ?? 0.0,
      scoreSource: (json['scoreSource'] as String?) ?? 'implicit',
      createdAt:
          DateTime.tryParse((json['createdAt'] as String?) ?? '') ??
          DateTime.now(),
    );
  }
}

class AssistantScoreAggregate {
  const AssistantScoreAggregate({
    required this.bucketDate,
    required this.scopeId,
    required this.domainId,
    required this.metricId,
    required this.scoreAvg,
    required this.sampleCount,
  });

  final String bucketDate;
  final String scopeId;
  final String domainId;
  final String metricId;
  final double scoreAvg;
  final int sampleCount;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'bucketDate': bucketDate,
      'scopeId': scopeId,
      'domainId': domainId,
      'metricId': metricId,
      'scoreAvg': scoreAvg,
      'sampleCount': sampleCount,
    };
  }

  factory AssistantScoreAggregate.fromJson(Map<String, dynamic> json) {
    return AssistantScoreAggregate(
      bucketDate: (json['bucketDate'] as String?) ?? '',
      scopeId: (json['scopeId'] as String?) ?? '',
      domainId: (json['domainId'] as String?) ?? 'general',
      metricId: (json['metricId'] as String?) ?? '',
      scoreAvg: (json['scoreAvg'] as num?)?.toDouble() ?? 0.0,
      sampleCount: (json['sampleCount'] as int?) ?? 0,
    );
  }
}

class AssistantLearningStore {
  AssistantLearningStore({String? storagePath})
    : _pathFuture = storagePath != null
          ? Future<String>.value(storagePath)
          : getAssistantStoragePath('learning_store.json');

  final Future<String> _pathFuture;
  final List<AssistantInteractionEvent> _events = <AssistantInteractionEvent>[];
  final List<AssistantInteractionMetricScore> _scores =
      <AssistantInteractionMetricScore>[];
  final List<AssistantScoreAggregate> _userDaily = <AssistantScoreAggregate>[];
  final List<AssistantScoreAggregate> _tagDomainDaily =
      <AssistantScoreAggregate>[];
  bool _loaded = false;

  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    final file = File(await _pathFuture);
    if (!await file.exists()) return;
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is! Map) return;

    final eventsRaw = decoded['events'];
    if (eventsRaw is List) {
      _events.addAll(
        eventsRaw.whereType<Map>().map(
          (item) => AssistantInteractionEvent.fromJson(
            item.cast<String, dynamic>(),
          ),
        ),
      );
    }
    final scoresRaw = decoded['scores'];
    if (scoresRaw is List) {
      _scores.addAll(
        scoresRaw.whereType<Map>().map(
          (item) => AssistantInteractionMetricScore.fromJson(
            item.cast<String, dynamic>(),
          ),
        ),
      );
    }
    final userRaw = decoded['userDaily'];
    if (userRaw is List) {
      _userDaily.addAll(
        userRaw.whereType<Map>().map(
          (item) => AssistantScoreAggregate.fromJson(
            item.cast<String, dynamic>(),
          ),
        ),
      );
    }
    final tagRaw = decoded['tagDomainDaily'];
    if (tagRaw is List) {
      _tagDomainDaily.addAll(
        tagRaw.whereType<Map>().map(
          (item) => AssistantScoreAggregate.fromJson(
            item.cast<String, dynamic>(),
          ),
        ),
      );
    }
  }

  Future<void> save() async {
    final file = File(await _pathFuture);
    await file.parent.create(recursive: true);
    await file.writeAsString(
      jsonEncode(<String, dynamic>{
        'events': _events.map((item) => item.toJson()).toList(growable: false),
        'scores': _scores.map((item) => item.toJson()).toList(growable: false),
        'userDaily': _userDaily
            .map((item) => item.toJson())
            .toList(growable: false),
        'tagDomainDaily': _tagDomainDaily
            .map((item) => item.toJson())
            .toList(growable: false),
      }),
    );
  }

  Future<void> appendEvent(AssistantInteractionEvent event) async {
    await load();
    _events.add(event);
    if (_events.length > 8000) {
      _events.removeRange(0, _events.length - 8000);
    }
  }

  Future<void> appendScores(List<AssistantInteractionMetricScore> scores) async {
    await load();
    _scores.addAll(scores);
    if (_scores.length > 16000) {
      _scores.removeRange(0, _scores.length - 16000);
    }
  }

  Future<void> replaceUserDaily(List<AssistantScoreAggregate> aggregates) async {
    await load();
    _userDaily
      ..clear()
      ..addAll(aggregates);
  }

  Future<void> replaceTagDomainDaily(
    List<AssistantScoreAggregate> aggregates,
  ) async {
    await load();
    _tagDomainDaily
      ..clear()
      ..addAll(aggregates);
  }

  Future<List<AssistantInteractionEvent>> events() async {
    await load();
    return List<AssistantInteractionEvent>.from(_events);
  }

  Future<List<AssistantInteractionMetricScore>> scores() async {
    await load();
    return List<AssistantInteractionMetricScore>.from(_scores);
  }

  Future<List<AssistantScoreAggregate>> userDaily() async {
    await load();
    return List<AssistantScoreAggregate>.from(_userDaily);
  }

  Future<List<AssistantScoreAggregate>> tagDomainDaily() async {
    await load();
    return List<AssistantScoreAggregate>.from(_tagDomainDaily);
  }
}

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
