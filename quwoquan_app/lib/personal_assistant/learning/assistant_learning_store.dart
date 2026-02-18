import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_models.dart';
import 'package:quwoquan_app/personal_assistant/storage/personal_assistant_storage_path.dart';

class AssistentLearningStore {
  AssistentLearningStore({
    String? storagePath,
  }) : _pathFuture = storagePath != null
            ? Future<String>.value(storagePath)
            : getPersonalAssistantStoragePath('learning_store.json');

  final Future<String> _pathFuture;

  final List<AssistentInteractionEvent> _events = <AssistentInteractionEvent>[];
  final List<AssistentInteractionMetricScore> _scores = <AssistentInteractionMetricScore>[];
  final List<AssistentScoreAggregate> _userDaily = <AssistentScoreAggregate>[];
  final List<AssistentScoreAggregate> _tagDomainDaily = <AssistentScoreAggregate>[];
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
        eventsRaw
            .whereType<Map>()
            .map((item) => AssistentInteractionEvent.fromJson(item.cast<String, dynamic>())),
      );
    }
    final scoresRaw = decoded['scores'];
    if (scoresRaw is List) {
      _scores.addAll(
        scoresRaw
            .whereType<Map>()
            .map((item) => AssistentInteractionMetricScore.fromJson(item.cast<String, dynamic>())),
      );
    }
    final userRaw = decoded['userDaily'];
    if (userRaw is List) {
      _userDaily.addAll(
        userRaw
            .whereType<Map>()
            .map((item) => AssistentScoreAggregate.fromJson(item.cast<String, dynamic>())),
      );
    }
    final tagRaw = decoded['tagDomainDaily'];
    if (tagRaw is List) {
      _tagDomainDaily.addAll(
        tagRaw
            .whereType<Map>()
            .map((item) => AssistentScoreAggregate.fromJson(item.cast<String, dynamic>())),
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
        'userDaily': _userDaily.map((item) => item.toJson()).toList(growable: false),
        'tagDomainDaily': _tagDomainDaily.map((item) => item.toJson()).toList(growable: false),
      }),
    );
  }

  Future<void> appendEvent(AssistentInteractionEvent event) async {
    await load();
    _events.add(event);
    if (_events.length > 8000) {
      _events.removeRange(0, _events.length - 8000);
    }
  }

  Future<void> appendScores(List<AssistentInteractionMetricScore> scores) async {
    await load();
    _scores.addAll(scores);
    if (_scores.length > 16000) {
      _scores.removeRange(0, _scores.length - 16000);
    }
  }

  Future<void> replaceUserDaily(List<AssistentScoreAggregate> aggregates) async {
    await load();
    _userDaily
      ..clear()
      ..addAll(aggregates);
  }

  Future<void> replaceTagDomainDaily(List<AssistentScoreAggregate> aggregates) async {
    await load();
    _tagDomainDaily
      ..clear()
      ..addAll(aggregates);
  }

  Future<List<AssistentInteractionEvent>> events() async {
    await load();
    return List<AssistentInteractionEvent>.from(_events);
  }

  Future<List<AssistentInteractionMetricScore>> scores() async {
    await load();
    return List<AssistentInteractionMetricScore>.from(_scores);
  }

  Future<List<AssistentScoreAggregate>> userDaily() async {
    await load();
    return List<AssistentScoreAggregate>.from(_userDaily);
  }

  Future<List<AssistentScoreAggregate>> tagDomainDaily() async {
    await load();
    return List<AssistentScoreAggregate>.from(_tagDomainDaily);
  }
}

