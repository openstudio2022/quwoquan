import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/assistant/scripted_assistant.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';

final class SearchAssistantRehearsalHandler implements RehearsalObjectHandler {
  const SearchAssistantRehearsalHandler();
  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) {
    if (invocation.operation.canonicalOperationId !=
        'assistant.assistant_run.StreamAssistantRunEvents') {
      return null;
    }
    return scriptedAssistantEventStream(invocation);
  }

  @override
  Future<Object?> handle(RehearsalInvocation i) async {
    switch (i.operation.canonicalOperationId) {
      case 'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery':
        return _executePersistedGraphQL(i);
      case 'gateway.persisted_query_execution.SearchPage':
        return _searchPage(i, i.body);
      case 'assistant.assistant_session.CreateAssistantSession':
        return i.store.commit(() {
          i.requireActor();
          final id = i.nextId('asst_');
          final now = i.now().toUtc().toIso8601String();
          final session = <String, Object?>{
            'sessionId': id,
            'userId': i.actorId,
            'state': 'active',
            'activeTurnId': '',
            'lastTurnId': '',
            'summary': '$rehearsalAssistantMarker 本地脚本会话',
            'summarySourceSequence': 0,
            'summaryVersion': 0,
            'createdAt': now,
            'updatedAt': now,
          };
          i.store.assistantSessions[id] = session;
          return session;
        });
      case 'assistant.assistant_session.GetAssistantSession':
        return _session(i, i.path('sessionId'));
      case 'assistant.assistant_session.ListAssistantSessions':
        return _listSessions(i);
      case 'assistant.assistant_run.GetAssistantRun':
        return _runWire(_run(i, i.path('runId')));
      case 'assistant.assistant_run.PauseAssistantRun':
        return _transitionRun(i, from: const {'running'}, to: 'paused');
      case 'assistant.assistant_run.ResumeAssistantRun':
        return _transitionRun(i, from: const {'paused'}, to: 'running');
      case 'assistant.assistant_run.SteerAssistantRun':
        return _steerRun(i);
      case 'assistant.assistant_task_view.ListAssistantTasks':
        return _listTasks(i);
      case 'assistant.assistant_turn_view.ListSessionTurns':
        return _listTurns(i);
      case 'assistant.skill_consent.GrantSkillConsent':
        return _grantConsent(i);
      case 'assistant.skill_consent.ListConsents':
        return _listConsents(i);
      case 'assistant.skill_consent.RevokeSkillConsent':
        return _revokeConsent(i);
      case 'assistant.skill_user_setting.PutSkillUserSetting':
        return _putSetting(i);
      case 'assistant.skill_user_setting.GetSkillUserSetting':
        return _getSetting(i);
      case 'assistant.skill_user_setting.ListSkillUserSettings':
        return _listSettings(i);
      case 'assistant.skill_subscription.CreateSkillSubscription':
        return _createSubscription(i);
      case 'assistant.skill_subscription.GetSkillSubscription':
        return _getSubscription(i);
      case 'assistant.skill_subscription.ListSkillSubscriptions':
        return _listSubscriptions(i);
      case 'assistant.skill_subscription.UpdateSkillSubscriptionStatus':
        return _updateSubscription(i);
      case 'assistant.skill_data_control_request.CreateSkillDataControlRequest':
        return _createDataControl(i);
      case 'assistant.skill_data_control_request.GetSkillDataControlRequest':
        return _getDataControl(i);
      case 'assistant.skill_data_control_request.ConfirmSkillDataControlRequest':
        return _confirmDataControl(i);
      case 'assistant.assistant_run.CancelAssistantRun':
        return i.store.commit(() {
          final run = i.store.assistantRuns[i.path('runId')];
          if (run == null || run['userId'] != i.actorId) {
            rehearsalUnauthorized();
          }
          if (!const {'completed', 'cancelled'}.contains(run['status'])) {
            run['cancelled'] = true;
            run['status'] = 'cancelled';
            run['revision'] = (run['revision'] as int) + 1;
            _finishTurn(i, run, 'cancelled');
          }
          return _runWire(run);
        });
      case 'assistant.assistant_run.StartAssistantRun':
        return i.store.commit(() {
          final sessionId = '${i.body['sessionId'] ?? i.path('sessionId')}';
          _session(i, sessionId);
          final active = i.store.assistantRuns.values.any(
            (row) =>
                row['sessionId'] == sessionId &&
                const {'running', 'paused'}.contains(row['status']),
          );
          if (active) _fail('ASSISTANT.USER.run_active_conflict');
          final id = i.nextId('run_');
          final turnId = i.nextId('turn_');
          final now = i.now().toUtc().toIso8601String();
          i.store.assistantRuns[id] = {
            'runId': id,
            'sessionId': sessionId,
            'userId': i.actorId,
            'status': 'running',
            'cancelled': false,
            'turnId': turnId,
            'goal': '${i.body['goal'] ?? i.body['inputText'] ?? ''}',
            'revision': 1,
            'createdAt': now,
            'scriptVersion': rehearsalAssistantScriptVersion,
          };
          _records(i, 'assistant.tasks')[turnId] = <String, Object?>{
            'taskId': turnId,
            'userId': i.actorId,
            'title': '${i.body['goal'] ?? i.body['inputText'] ?? '本地助手任务'}',
            'description': rehearsalAssistantMarker,
            'status': 'running',
            'sourceSkillId': i.body['skillId'],
            'updatedAt': now,
          };
          _records(i, 'assistant.turns')[turnId] = <String, Object?>{
            'turnId': turnId,
            'sessionId': sessionId,
            'userId': i.actorId,
            'status': 'running',
            'inputText': '${i.body['goal'] ?? i.body['inputText'] ?? ''}',
            'createdAt': now,
          };
          final session = i.store.assistantSessions[sessionId]!;
          session['activeTurnId'] = turnId;
          session['lastTurnId'] = turnId;
          session['updatedAt'] = now;
          return _runWire(i.store.assistantRuns[id]!);
        });
      default:
        return rehearsalUnsupported();
    }
  }

  Future<Object?> _transitionRun(
    RehearsalInvocation i, {
    required Set<String> from,
    required String to,
  }) => i.store.commit(() {
    final run = _run(i, i.path('runId'));
    if (!from.contains(run['status'])) {
      _fail('ASSISTANT.USER.run_state_conflict');
    }
    run['status'] = to;
    run['revision'] = (run['revision'] as int) + 1;
    final turn = _records(i, 'assistant.turns')['${run['turnId']}'];
    if (turn != null) turn['status'] = to;
    final task = _records(i, 'assistant.tasks')['${run['turnId']}'];
    if (task != null) {
      task['status'] = to;
      task['updatedAt'] = i.now().toUtc().toIso8601String();
    }
    return _runWire(run);
  });

  Future<Object?> _steerRun(RehearsalInvocation i) => i.store.commit(() {
    final run = _run(i, i.path('runId'));
    if (run['status'] != 'running') _fail('ASSISTANT.USER.run_state_conflict');
    final goal = '${i.body['goal'] ?? i.body['instruction'] ?? ''}'.trim();
    if (goal.isEmpty) _fail('ASSISTANT.USER.run_invalid_argument');
    run['goal'] = goal;
    run['revision'] = (run['revision'] as int) + 1;
    return _runWire(run);
  });

  void _finishTurn(
    RehearsalInvocation i,
    Map<String, Object?> run,
    String status,
  ) {
    final now = i.now().toUtc().toIso8601String();
    final turn = _records(i, 'assistant.turns')['${run['turnId']}'];
    if (turn != null) {
      turn['status'] = status;
      turn['completedAt'] = now;
    }
    final task = _records(i, 'assistant.tasks')['${run['turnId']}'];
    if (task != null) {
      task['status'] = status;
      task['updatedAt'] = now;
    }
    final session = i.store.assistantSessions['${run['sessionId']}'];
    if (session != null) {
      session['activeTurnId'] = '';
      session['updatedAt'] = now;
    }
  }

  Future<Object?> _listSessions(RehearsalInvocation i) async {
    i.requireActor();
    final rows =
        i.store.assistantSessions.values
            .where((r) => r['userId'] == i.actorId)
            .toList()
          ..sort((a, b) => '${b['updatedAt']}'.compareTo('${a['updatedAt']}'));
    return _page(i, rows, maximum: 50);
  }

  Map<String, Object?> _run(RehearsalInvocation i, String id) {
    i.requireActor();
    final row = i.store.assistantRuns[id];
    if (row == null) _fail('ASSISTANT.USER.run_not_found');
    if (row['userId'] != i.actorId) _fail('ASSISTANT.USER.run_unauthorized');
    return row;
  }

  Map<String, Object?> _runWire(Map<String, Object?> r) => <String, Object?>{
    'runId': r['runId'],
    'sessionId': r['sessionId'],
    'status': r['status'],
    'reasoningProfile': r['reasoningProfile'] ?? 'balanced',
    'goal': r['goal'] ?? '',
    'traceId': 'rehearsal',
    'revision': r['revision'] ?? 1,
    'streamState': const <String, Object?>{},
    'createdAt': r['createdAt'],
    'completedAt': r['completedAt'] ?? '',
  };
  Future<Object?> _listTurns(RehearsalInvocation i) async {
    final session = _session(i, i.path('sessionId'));
    final rows = _records(i, 'assistant.turns').values
        .where(
          (r) =>
              r['sessionId'] == session['sessionId'] &&
              r['userId'] == i.actorId,
        )
        .map(
          (r) => <String, Object?>{
            'turnId': r['turnId'],
            'sessionId': r['sessionId'],
            'status': r['status'],
            'inputText': r['inputText'],
            'skillId': r['skillId'],
            'domainId': r['domainId'],
            'createdAt': r['createdAt'],
            'completedAt': r['completedAt'],
          },
        )
        .toList();
    return _page(i, rows, maximum: 50);
  }

  Future<Object?> _listTasks(RehearsalInvocation i) async {
    i.requireActor();
    final status = i.query('status');
    final rows = _records(i, 'assistant.tasks').values
        .where(
          (r) =>
              r['userId'] == i.actorId &&
              (status.isEmpty || r['status'] == status),
        )
        .map(
          (r) => <String, Object?>{
            'taskId': r['taskId'],
            'title': r['title'],
            'description': r['description'],
            'status': r['status'],
            'dueAt': r['dueAt'],
            'priority': r['priority'],
            'sourceSkillId': r['sourceSkillId'],
            'updatedAt': r['updatedAt'],
          },
        )
        .toList();
    final limit = (int.tryParse(i.query('limit')) ?? 20).clamp(1, 50);
    return <String, Object?>{'items': rows.take(limit).toList()};
  }

  Future<Object?> _grantConsent(RehearsalInvocation i) => i.store.commit(() {
    i.requireActor();
    final skill = _requiredPath(i, 'skillId');
    final scopes = _strings(i.body['grantedScopes'] ?? i.body['scopes']);
    final key = '${i.actorId}::$skill';
    final table = _records(i, 'assistant.consents');
    final now = i.now().toUtc().toIso8601String();
    final old = table[key];
    final row = <String, Object?>{
      'id': old?['id'] ?? i.nextId('consent_'),
      'accountId': i.actorId,
      'skillId': skill,
      'grantedScopes': scopes,
      'grantedAt': now,
      'revokedAt': null,
      'granted': true,
    };
    table[key] = row;
    return <String, Object?>{'consent': row, 'replayed': false};
  });
  Future<Object?> _listConsents(RehearsalInvocation i) async {
    i.requireActor();
    return <String, Object?>{
      'items': _records(
        i,
        'assistant.consents',
      ).values.where((r) => r['accountId'] == i.actorId).toList(),
    };
  }

  Future<Object?> _revokeConsent(RehearsalInvocation i) => i.store.commit(() {
    i.requireActor();
    final skill = _requiredPath(i, 'skillId');
    final row = _records(i, 'assistant.consents')['${i.actorId}::$skill'];
    if (row == null) _fail('ASSISTANT.USER.consent_invalid_argument');
    row['granted'] = false;
    row['revokedAt'] = i.now().toUtc().toIso8601String();
    return <String, Object?>{
      'status': 'revoked',
      'skillId': skill,
      'replayed': false,
    };
  });
  Future<Object?> _putSetting(RehearsalInvocation i) => i.store.commit(() {
    i.requireActor();
    final skill = _requiredPath(i, 'skillId');
    final table = _records(i, 'assistant.settings');
    final key = '${i.actorId}::$skill';
    final old = table[key];
    final now = i.now().toUtc().toIso8601String();
    final row = <String, Object?>{
      'id': old?['id'] ?? i.nextId('setting_'),
      'accountId': i.actorId,
      'skillId': skill,
      'status': i.body['status'] ?? 'enabled',
      'configurationData':
          i.body['configurationData'] ?? const <String, Object?>{},
      'configurationSchemaDigest':
          i.body['configurationSchemaDigest'] ?? 'rehearsal:v1',
      'memoryPolicy': i.body['memoryPolicy'] ?? 'package_default',
      'connectorConnectionRefs':
          i.body['connectorConnectionRefs'] ?? const <String>[],
      'revision': ((old?['revision'] as int?) ?? 0) + 1,
      'createdAt': old?['createdAt'] ?? now,
      'updatedAt': now,
    };
    table[key] = row;
    return <String, Object?>{
      'setting': row,
      'changed': true,
      'replayed': false,
    };
  });
  Future<Object?> _getSetting(RehearsalInvocation i) async {
    i.requireActor();
    final row = _records(
      i,
      'assistant.settings',
    )['${i.actorId}::${_requiredPath(i, 'skillId')}'];
    if (row == null) _fail('ASSISTANT.USER.skill_setting_not_found');
    return row;
  }

  Future<Object?> _listSettings(RehearsalInvocation i) async {
    i.requireActor();
    final limit = (int.tryParse(i.query('limit')) ?? 20).clamp(1, 100);
    return <String, Object?>{
      'items': _records(
        i,
        'assistant.settings',
      ).values.where((r) => r['accountId'] == i.actorId).take(limit).toList(),
    };
  }

  Future<Object?> _createSubscription(
    RehearsalInvocation i,
  ) => i.store.commit(() {
    i.requireActor();
    final skill = '${i.body['skillId'] ?? ''}'.trim();
    if (skill.isEmpty) _fail('ASSISTANT.USER.subscription_invalid_argument');
    final id = i.nextId('subscription_');
    final now = i.now().toUtc().toIso8601String();
    final row = <String, Object?>{
      'subscriptionId': id,
      'version': 1,
      'owner': <String, Object?>{
        'ownerUserId': i.actorId,
        'ownerPersonaId': i.actorId,
      },
      'createdByUserId': i.actorId,
      'createdByPersonaId': i.actorId,
      'skillId': skill,
      'domainId': i.body['domainId'] ?? 'rehearsal',
      'tagRefs': i.body['tagRefs'] ?? const <String>[],
      'status': 'active',
      'searchQueryPlan': i.body['searchQueryPlan'] ?? const <String, Object?>{},
      'trigger':
          i.body['trigger'] ?? const <String, Object?>{'timezone': 'UTC'},
      'destination': i.body['destination'] ?? const <String, Object?>{},
      'deliveryState': const <String, Object?>{},
      'createdAt': now,
      'updatedAt': now,
    };
    _records(i, 'assistant.subscriptions')[id] = row;
    return row;
  });
  Future<Object?> _getSubscription(RehearsalInvocation i) async {
    i.requireActor();
    final row = _records(
      i,
      'assistant.subscriptions',
    )[i.path('subscriptionId')];
    if (row == null) _fail('ASSISTANT.USER.subscription_not_found');
    if (row['createdByPersonaId'] != i.actorId) {
      _fail('ASSISTANT.USER.subscription_unauthorized');
    }
    return row;
  }

  Future<Object?> _listSubscriptions(RehearsalInvocation i) async {
    i.requireActor();
    final status = i.query('status');
    final limit = (int.tryParse(i.query('limit')) ?? 20).clamp(1, 100);
    return <String, Object?>{
      'items': _records(i, 'assistant.subscriptions').values
          .where(
            (r) =>
                r['createdByPersonaId'] == i.actorId &&
                (status.isEmpty || r['status'] == status),
          )
          .take(limit)
          .toList(),
    };
  }

  Future<Object?> _updateSubscription(RehearsalInvocation i) => i.store.commit(
    () {
      final row = _ownedRecord(
        i,
        'assistant.subscriptions',
        i.path('subscriptionId'),
        'createdByPersonaId',
        'ASSISTANT.USER.subscription_not_found',
        'ASSISTANT.USER.subscription_unauthorized',
      );
      final next = '${i.body['status'] ?? ''}';
      final current = '${row['status']}';
      final allowed =
          (current == 'active' && next == 'paused') ||
          (current == 'paused' && next == 'active') ||
          ((current == 'active' || current == 'paused') && next == 'archived');
      if (!allowed) _fail('ASSISTANT.USER.subscription_invalid_transition');
      row['status'] = next;
      row['version'] = (row['version'] as int) + 1;
      row['updatedAt'] = i.now().toUtc().toIso8601String();
      return row;
    },
  );
  Future<Object?> _createDataControl(
    RehearsalInvocation i,
  ) => i.store.commit(() {
    i.requireActor();
    final skill = _requiredPath(i, 'skillId');
    final actions = _strings(i.body['requestedActions']);
    final allowed = {'delete_memory', 'delete_configuration', 'revoke_consent'};
    if (actions.any((a) => !allowed.contains(a))) {
      _fail('ASSISTANT.USER.skill_data_control_invalid_argument');
    }
    final id = i.nextId('data_');
    final now = i.now().toUtc().toIso8601String();
    final row = <String, Object?>{
      'requestId': id,
      'ownerId': i.actorId,
      'skillId': skill,
      'requestedActions': actions,
      'completedActions': <String>[],
      'status': 'pending_confirmation',
      'createdAt': now,
      'updatedAt': now,
      'revision': 1,
    };
    _records(i, 'assistant.data_control')[id] = row;
    return <String, Object?>{'request': _publicData(row), 'replayed': false};
  });
  Future<Object?> _getDataControl(RehearsalInvocation i) async {
    final row = _ownedRecord(
      i,
      'assistant.data_control',
      i.path('requestId'),
      'ownerId',
      'ASSISTANT.USER.skill_data_control_not_found',
      'ASSISTANT.USER.skill_data_control_unauthorized',
    );
    return _publicData(row);
  }

  Future<Object?> _confirmDataControl(RehearsalInvocation i) => i.store.commit(
    () {
      final row = _ownedRecord(
        i,
        'assistant.data_control',
        i.path('requestId'),
        'ownerId',
        'ASSISTANT.USER.skill_data_control_not_found',
        'ASSISTANT.USER.skill_data_control_unauthorized',
      );
      if (row['status'] != 'pending_confirmation') {
        _fail('ASSISTANT.USER.skill_data_control_revision_conflict');
      }
      final actions = List<String>.from(row['requestedActions'] as List);
      final skill = row['skillId'];
      for (final action in actions) {
        if (action == 'delete_configuration') {
          _records(i, 'assistant.settings').remove('${i.actorId}::$skill');
        }
        if (action == 'revoke_consent') {
          _records(i, 'assistant.consents').remove('${i.actorId}::$skill');
        }
        if (action == 'delete_memory') {
          _records(i, 'assistant.tasks').removeWhere(
            (_, r) => r['userId'] == i.actorId && r['sourceSkillId'] == skill,
          );
        }
      }
      final now = i.now().toUtc().toIso8601String();
      row['completedActions'] = actions;
      row['status'] = 'completed';
      row['confirmedAt'] = now;
      row['completedAt'] = now;
      row['updatedAt'] = now;
      row['revision'] = (row['revision'] as int) + 1;
      return <String, Object?>{'request': _publicData(row), 'replayed': false};
    },
  );
  Map<String, Object?> _publicData(Map<String, Object?> row) =>
      Map<String, Object?>.from(row)..remove('ownerId');
  Map<String, Object?> _ownedRecord(
    RehearsalInvocation i,
    String table,
    String id,
    String owner,
    String notFound,
    String unauthorized,
  ) {
    i.requireActor();
    final row = _records(i, table)[id];
    if (row == null) _fail(notFound);
    if (row[owner] != i.actorId) _fail(unauthorized);
    return row;
  }

  Map<String, Map<String, Object?>> _records(
    RehearsalInvocation i,
    String key,
  ) => i.store.records.putIfAbsent(key, () => <String, Map<String, Object?>>{});
  String _requiredPath(RehearsalInvocation i, String key) {
    final value = i.path(key).trim();
    if (value.isEmpty) _fail('ASSISTANT.USER.run_invalid_argument');
    return value;
  }

  List<String> _strings(Object? value) {
    if (value is! List || value.isEmpty) {
      _fail('ASSISTANT.USER.run_invalid_argument');
    }
    return value
        .map((e) => '$e'.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();
  }

  Map<String, Object?> _page(
    RehearsalInvocation i,
    List<Map<String, Object?>> rows, {
    required int maximum,
  }) {
    final limit = (int.tryParse(i.query('limit')) ?? 20).clamp(1, maximum);
    final cursor = i.query('cursor');
    var offset = 0;
    if (cursor.isNotEmpty) {
      try {
        final d = jsonDecode(
          utf8.decode(base64Url.decode(base64Url.normalize(cursor))),
        ) as Map;
        if (d['actor'] != i.actorId) throw const FormatException();
        offset = d['offset'] as int;
      } catch (_) {
        _fail('ASSISTANT.USER.session_invalid_argument');
      }
    }
    final end = (offset + limit).clamp(0, rows.length);
    return <String, Object?>{
      'items': rows.sublist(offset, end),
      if (end < rows.length)
        'nextCursor': base64Url.encode(
          utf8.encode(jsonEncode({'actor': i.actorId, 'offset': end})),
        ),
    };
  }

  Never _fail(String code) => throw CloudErrorMapper.fromDecodedStatusCode(
    400,
    body: <String, Object?>{'code': code},
  );

  Future<Object?> _executePersistedGraphQL(RehearsalInvocation i) async {
    final body = i.body;
    if (body.keys.toSet().difference(const {
          'operationName',
          'variables',
          'extensions',
        }).isNotEmpty ||
        body['operationName'] != 'SearchPage') {
      _invalidSearchRequest();
    }
    final variables = _object(body['variables']);
    final extensions = _object(body['extensions']);
    final persistedQuery = _object(extensions['persistedQuery']);
    if (variables.length != 1 ||
        !variables.containsKey('input') ||
        extensions.length != 1 ||
        persistedQuery.length != 2 ||
        persistedQuery['version'] != 1 ||
        persistedQuery['sha256Hash'] !=
            '111b715594655786eba342c5cbebe7ea1338a9cf016ed0f35f54096802583478') {
      _invalidSearchRequest();
    }
    final page = await _searchPage(i, _object(variables['input']));
    return <String, Object?>{
      'data': <String, Object?>{'searchPage': page},
    };
  }

  Future<Map<String, Object?>> _searchPage(
    RehearsalInvocation i,
    Map<String, Object?> input,
  ) async {
    final allowed = const {
      'query',
      'first',
      'after',
      'objectTypes',
      'contentTypes',
    };
    if (input.keys.toSet().difference(allowed).isNotEmpty) {
      _invalidSearchRequest();
    }
    final rawQuery = input['query'];
    if (rawQuery is! String) _invalidSearchRequest();
    final query = (rawQuery).trim().toLowerCase();
    if (query.isEmpty ||
        utf8.encode(query).length > 1024 ||
        query.runes.any((rune) => rune < 32 || rune == 127)) {
      _invalidSearchRequest();
    }
    final firstValue = input['first'];
    final first = firstValue ?? 20;
    if (first is! int || first < 1 || first > 20) {
      _invalidSearchRequest();
    }
    final objectTypes = _enumList(input['objectTypes'], const {
      'CIRCLE',
      'CIRCLE_GROUP',
      'CONTENT_POST',
      'ENTITY_HOMEPAGE',
      'LOCATION_PLACE',
      'USER_PROFILE',
    });
    final contentTypes = _enumList(input['contentTypes'], const {
      'ARTICLE',
      'IMAGE',
      'VIDEO',
    });
    final canonicalContentTypes = contentTypes
        .map((value) => value.toLowerCase())
        .toSet();
    final offset = _cursorOffset(
      input['after'],
      actor: i.actorId,
      query: query,
      objectTypes: objectTypes,
      contentTypes: contentTypes,
    );

    final bundle = await OfflineContentBundle.load();
    final matches =
        objectTypes.isNotEmpty && !objectTypes.contains('CONTENT_POST')
        ? <Map<String, Object?>>[]
        : bundle
              .rows('posts')
              .map((row) => _object(row['projection']))
              .where((post) {
                final contentType = '${post['contentType'] ?? ''}'.trim();
                if (canonicalContentTypes.isNotEmpty &&
                    !canonicalContentTypes.contains(contentType)) {
                  return false;
                }
                final searchable = <Object?>[
                  post['title'],
                  post['summary'],
                  post['body'],
                  post['authorDisplayName'],
                ].map((value) => '${value ?? ''}'.toLowerCase()).join('\n');
                return searchable.contains(query);
              })
              .toList(growable: false);
    if (offset > matches.length) _invalidSearchRequest();
    final end = (offset + first).clamp(0, matches.length);
    final items = <Map<String, Object?>>[];
    for (var index = offset; index < end; index += 1) {
      final post = matches[index];
      final postId = '${post['postId'] ?? ''}'.trim();
      final title = '${post['title'] ?? ''}'.trim();
      final contentType = '${post['contentType'] ?? ''}'.trim();
      if (postId.isEmpty ||
          title.isEmpty ||
          !const {'article', 'image', 'video'}.contains(contentType)) {
        _invalidSearchRequest();
      }
      final thumbnailUrl = '${post['thumbnailUrl'] ?? post['coverUrl'] ?? ''}'
          .trim();
      final thumbnailAssetId = _thumbnailAssetId(post);
      items.add(<String, Object?>{
        'objectRef': base64Url.encode(
          utf8.encode(
            jsonEncode(<String, String>{
              'objectType': 'content.post',
              'objectId': postId,
            }),
          ),
        ),
        'resultType': 'CONTENT_POST',
        'contentType': contentType.toUpperCase(),
        'title': title,
        if ('${post['summary'] ?? ''}'.trim().isNotEmpty)
          'snippet': '${post['summary']}'.trim(),
        if (thumbnailUrl.isNotEmpty) 'thumbnailUrl': thumbnailUrl,
        if (thumbnailAssetId.isNotEmpty) 'thumbnailAssetId': thumbnailAssetId,
        if (thumbnailUrl.isNotEmpty) 'thumbnailAccessMode': 'public',
        'action': AppLinkTemplates.postAppDeepLink(postId),
        'rankPosition': index,
        'rankReason': 'bundled_canonical_match',
      });
    }
    final facetCounts = <String, int>{};
    for (final post in matches) {
      final key = '${post['contentType'] ?? ''}'.trim().toUpperCase();
      if (key.isNotEmpty) facetCounts[key] = (facetCounts[key] ?? 0) + 1;
    }
    return <String, Object?>{
      'items': items,
      'facets': <Map<String, Object?>>[
        for (final entry in facetCounts.entries)
          <String, Object?>{'key': entry.key, 'count': entry.value},
      ],
      'suggestions': const <String>[],
      'matchedTerms': matches.isEmpty ? const <String>[] : <String>[query],
      'degradeSignals': const <Map<String, Object?>>[],
      'searchRequestId': i.nextId('alpha_search_'),
      'nextCursor': end < matches.length
          ? _encodeCursor(
              actor: i.actorId,
              query: query,
              objectTypes: objectTypes,
              contentTypes: contentTypes,
              offset: end,
            )
          : null,
    };
  }

  Map<String, Object?> _object(Object? value) {
    if (value is! Map) _invalidSearchRequest();
    return <String, Object?>{
      for (final entry in (value).entries) '${entry.key}': entry.value,
    };
  }

  Set<String> _enumList(Object? value, Set<String> allowed) {
    if (value == null) return <String>{};
    if (value is! List || value.length > allowed.length) {
      _invalidSearchRequest();
    }
    final result = <String>{};
    for (final item in value) {
      if (item is! String || !allowed.contains(item) || !result.add(item)) {
        _invalidSearchRequest();
      }
    }
    return result;
  }

  int _cursorOffset(
    Object? value, {
    required String actor,
    required String query,
    required Set<String> objectTypes,
    required Set<String> contentTypes,
  }) {
    if (value == null) return 0;
    if (value is! String || value.isEmpty || value.trim() != value) {
      _invalidSearchRequest();
    }
    try {
      final cursor = _object(
        jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(value)))),
      );
      if (cursor.length != 5 ||
          cursor['actor'] != actor ||
          cursor['query'] != query ||
          cursor['objectTypes'] != _sortedKey(objectTypes) ||
          cursor['contentTypes'] != _sortedKey(contentTypes) ||
          cursor['offset'] is! int ||
          (cursor['offset'] as int) < 0) {
        _invalidSearchRequest();
      }
      return cursor['offset'] as int;
    } catch (_) {
      _invalidSearchRequest();
    }
  }

  String _encodeCursor({
    required String actor,
    required String query,
    required Set<String> objectTypes,
    required Set<String> contentTypes,
    required int offset,
  }) => base64Url.encode(
    utf8.encode(
      jsonEncode(<String, Object?>{
        'actor': actor,
        'query': query,
        'objectTypes': _sortedKey(objectTypes),
        'contentTypes': _sortedKey(contentTypes),
        'offset': offset,
      }),
    ),
  );

  String _sortedKey(Set<String> values) => (values.toList()..sort()).join(',');

  String _thumbnailAssetId(Map<String, Object?> post) {
    final mediaItems = post['mediaItems'];
    if (mediaItems is List &&
        mediaItems.isNotEmpty &&
        mediaItems.first is Map) {
      final first = _object(mediaItems.first);
      final cover = '${first['coverAssetId'] ?? ''}'.trim();
      if (cover.isNotEmpty) return cover;
    }
    return '${post['mediaAssetId'] ?? ''}'.trim();
  }

  Never _invalidSearchRequest() => throw CloudErrorMapper.fromDecodedStatusCode(
    400,
    body: const <String, Object?>{
      'code': 'GATEWAY.USER.graphql_request_invalid',
    },
  );

  Map<String, Object?> _session(RehearsalInvocation i, String id) {
    final session = i.store.assistantSessions[id];
    if (session == null || session['userId'] != i.actorId) {
      rehearsalUnauthorized();
    }
    return session;
  }
}
