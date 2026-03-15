import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/learning/domain/assistant_learning_models.dart';
import 'package:quwoquan_app/assistant/memory/storage/assistant_storage_path.dart';

class AssistantLearningStore {
  AssistantLearningStore({String? storagePath})
    : _pathFuture = storagePath != null
          ? Future<String>.value(storagePath)
          : getPersonalAssistantStoragePath('learning_store.json');

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
