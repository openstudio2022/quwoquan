import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_handler_support.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';

final class GatheringRehearsalHandler {
  const GatheringRehearsalHandler();

  Future<Object?> handle(RehearsalInvocation i) {
    final op = i.operation.canonicalOperationId;
    if (op == 'circle.gathering.CreateGatheringDraft') return _create(i);
    if (op == 'circle.gathering.GetGathering') return _private(i);
    if (op == 'circle.gathering.GetPublicGathering') return _public(i);
    if (op.startsWith('circle.gathering.List')) return _list(i, op);
    if (op == 'circle.gathering_plan.GetGatheringPlan') return _plan(i);
    if (op == 'circle.gathering_plan.ListGatheringPlanRevisions')
      return _revisions(i);
    return _command(i, op);
  }

  Map<String, Map<String, Object?>> _g(RehearsalInvocation i) =>
      circleTable(i, 'gatherings');
  Map<String, Map<String, Object?>> _p(RehearsalInvocation i) =>
      circleTable(i, 'gathering_participations');
  Map<String, Map<String, Object?>> _plans(RehearsalInvocation i) =>
      circleTable(i, 'gathering_plans');

  Future<Object?> _create(RehearsalInvocation i) => i.store.commit(() {
    i.requireActor();
    final host = i.body['hostBinding'];
    if (host is! Map || '${host['hostSubjectId'] ?? ''}'.isEmpty)
      circleFailure('gathering_host_authority_invalid');
    final id = i.nextId('gathering_'),
        rid = i.nextId('grev_'),
        now = nowWire(i);
    final policy = Map<String, Object?>.from(
      i.body['policySet'] as Map? ?? const {},
    );
    final row = <String, Object?>{
      'gatheringId': id,
      'aggregateVersion': 1,
      'createdByPersonaId': i.actorId,
      'hostBinding': cloneRehearsalValue(host),
      'organizerAssignments': [
        {
          'personaId': i.actorId,
          'role': 'primary_organizer',
          'authorityEvidenceRef': 'rehearsal:creator',
          'authorityVersion': 1,
          'assignedAt': now,
          'version': 1,
        },
      ],
      'purpose': cloneRehearsalValue(i.body['purpose'] ?? _purpose()),
      'schedule': cloneRehearsalValue(i.body['schedule'] ?? {}),
      'place': cloneRehearsalValue(i.body['place'] ?? {'mode': 'physical'}),
      'policySet': cloneRehearsalValue(policy.isEmpty ? _policy() : policy),
      'admissionControl': {'status': 'open', 'version': 1},
      'lifecycleStatus': 'draft',
      'roomBindingStatus': 'not_required',
      'currentGatheringRevisionId': rid,
      'currentGatheringRevisionNumber': 1,
      'watchVersion': 0,
      'createdAt': now,
      'updatedAt': now,
    };
    _g(i)[id] = row;
    final revision = _revision(rid, 1, i.actorId, now);
    _plans(i)[id] = {
      'id': 'plan_$id',
      'gatheringId': id,
      'version': 1,
      'currentRevisionId': rid,
      'currentRevisionNumber': 1,
      'currentRevisionDigest': 'digest:$rid',
      'revisions': [revision],
      'proposals': <Object>[],
      'acknowledgements': <Object>[],
      'createdAt': now,
      'updatedAt': now,
    };
    if (i.body['creatorParticipates'] == true)
      _p(i)[gatheringParticipationKey(id, i.actorId)] = _participation(
        i,
        id,
        i.actorId,
        'active',
      );
    return _result(i, row);
  });

  Future<Object?> _command(RehearsalInvocation i, String op) => i.store.commit(
    () {
      final id = requiredCirclePath(i, 'gatheringId'),
          row = requireRow(_g(i), id, 'gathering_not_found');
      requireVersion(
        row,
        i.body['expectedGatheringVersion'],
        'gathering_version_conflict',
      );
      final mine = _p(i)[gatheringParticipationKey(id, i.actorId)];
      if (op == 'circle.gathering.JoinOpenGathering' ||
          op == 'circle.gathering.ApplyToGathering' ||
          op == 'circle.gathering.AcceptGatheringInvitation' ||
          op == 'circle.gathering.DeclineGatheringInvitation' ||
          op == 'circle.gathering.CompleteGatheringSelf' ||
          op == 'circle.gathering.WatchGatheringAvailability') {
        if (op.endsWith('WatchGatheringAvailability')) {
          if (_closed(row)) circleFailure('gathering_transition_forbidden');
          final expected = bodyInt(i, 'expectedWatchVersion');
          if (expected != ((mine?['watchVersion'] as num?)?.toInt() ?? 0))
            circleFailure('gathering_version_conflict');
          final target = mine ?? _participation(i, id, i.actorId, 'closed');
          target['watchVersion'] = expected + 1;
          target['watching'] = true;
          _p(i)[gatheringParticipationKey(id, i.actorId)] = target;
          return _result(i, row, participation: target);
        }
        if (op.endsWith('ApplyToGathering')) {
          _ensureAdmission(i, row, allow: 'approval');
          final r = _participation(i, id, i.actorId, 'application_pending');
          r['answers'] = cloneRehearsalValue(
            i.body['answers'] ?? const <Object>[],
          );
          _p(i)[gatheringParticipationKey(id, i.actorId)] = r;
          return _result(i, row, participation: r);
        }
        if (op.endsWith('JoinOpenGathering')) {
          _ensureAdmission(i, row, allow: 'open');
          final r = _participation(i, id, i.actorId, 'active');
          _p(i)[gatheringParticipationKey(id, i.actorId)] = r;
          return _result(i, row, participation: r);
        }
        if (op.endsWith('AcceptGatheringInvitation')) {
          if (mine?['state'] != 'invited_pending')
            circleFailure('gathering_invitation_inactive');
          _ensureAdmission(i, row);
          mine!['state'] = 'active';
          mine['version'] = rowVersion(mine) + 1;
          mine['updatedAt'] = nowWire(i);
          return _result(i, row, participation: mine);
        }
        if (op.endsWith('DeclineGatheringInvitation')) {
          if (mine?['state'] != 'invited_pending')
            circleFailure('gathering_invitation_inactive');
          mine!['state'] = 'closed';
          mine['version'] = rowVersion(mine) + 1;
          mine['updatedAt'] = nowWire(i);
          return _result(i, row, participation: mine);
        }
        if (mine?['state'] != 'active')
          circleFailure('gathering_active_participation_required');
        mine!['attendanceDeclared'] = true;
        mine['version'] = rowVersion(mine) + 1;
        return _result(i, row, participation: mine);
      }
      if (!_organizer(row, i.actorId) &&
          op != 'circle.gathering.SafetyTerminateGathering')
        circleFailure('gathering_permission_denied');
      if (op == 'circle.gathering.SafetyTerminateGathering') {
        final authority = circleTable(
          i,
          'gathering_safety_authorities',
        )[i.actorId];
        if (authority?['active'] != true)
          circleFailure('gathering_safety_termination_denied');
        row['lifecycleStatus'] = 'completed';
        row['outcomeStatus'] = 'safety_terminated';
      } else if (op == 'circle.gathering.PublishGathering') {
        if (row['lifecycleStatus'] != 'draft')
          circleFailure('gathering_transition_forbidden');
        row['lifecycleStatus'] = 'published';
      } else if (op == 'circle.gathering.CancelGathering') {
        if (_closed(row)) circleFailure('gathering_transition_forbidden');
        row['lifecycleStatus'] = 'cancelled';
        row['outcomeStatus'] = 'did_not_happen';
      } else if (op == 'circle.gathering.CompleteGathering') {
        if (row['lifecycleStatus'] != 'published')
          circleFailure('gathering_transition_forbidden');
        row['lifecycleStatus'] = 'completed';
        row['outcomeStatus'] = 'occurred';
      } else if (op == 'circle.gathering.EndGatheringEarly') {
        if (row['lifecycleStatus'] != 'published')
          circleFailure('gathering_operation_not_allowed_in_progress');
        row['lifecycleStatus'] = 'completed';
        row['outcomeStatus'] = 'ended_early';
      } else if (op == 'circle.gathering.PauseGatheringAdmission') {
        if (_closed(row)) circleFailure('gathering_transition_forbidden');
        final c = row['admissionControl'] as Map;
        c['status'] = 'paused';
        c['pausedByPersonaId'] = i.actorId;
        c['reasonRef'] = i.body['reasonRef'];
        c['pausedAt'] = nowWire(i);
        c['version'] = ((c['version'] as num).toInt()) + 1;
      } else if (op == 'circle.gathering.ResumeGatheringAdmission') {
        final c = row['admissionControl'] as Map;
        if (c['status'] != 'paused')
          circleFailure('gathering_transition_forbidden');
        c
          ..['status'] = 'open'
          ..remove('pausedByPersonaId')
          ..remove('reasonRef')
          ..remove('pausedAt');
        c['version'] = ((c['version'] as num).toInt()) + 1;
      } else if (op == 'circle.gathering.ChangeGatheringCapacity') {
        final max = bodyInt(i, 'maxParticipants');
        if (max < _occupied(i, id) || max < 1)
          circleFailure('gathering_capacity_below_occupied_seats');
        (row['policySet'] as Map)['capacityPolicy'] = {'maxParticipants': max};
        _newRevision(i, row);
      } else if (op == 'circle.gathering.UpdateGathering') {
        for (final k in [
          'hostBinding',
          'purpose',
          'schedule',
          'place',
          'policySet',
        ])
          if (i.body.containsKey(k)) row[k] = cloneRehearsalValue(i.body[k]);
        _newRevision(i, row);
      } else if (op == 'circle.gathering.InviteToGathering') {
        _ensureAdmission(i, row);
        final pid = requiredCircleBody(i, 'participantPersonaId');
        final r = _participation(i, id, pid, 'invited_pending');
        r['seatHoldUntil'] = i.body['seatHoldUntil'];
        _p(i)[gatheringParticipationKey(id, pid)] = r;
      } else if (op == 'circle.gathering.ReviewGatheringApplication') {
        final pid = requiredCircleBody(i, 'participantPersonaId'),
            r = requireRow(
              _p(i),
              gatheringParticipationKey(id, pid),
              'gathering_participation_conflict',
            );
        if (r['state'] != 'application_pending')
          circleFailure('gathering_participation_conflict');
        if (i.body['decision'] == 'approve') {
          _ensureAdmission(i, row);
          r['state'] = 'active';
        } else
          r['state'] = 'closed';
        r['version'] = rowVersion(r) + 1;
        r['updatedAt'] = nowWire(i);
      } else if (op == 'circle.gathering.RemoveGatheringParticipant') {
        final pid = requiredCircleBody(i, 'participantPersonaId'),
            r = requireRow(
              _p(i),
              gatheringParticipationKey(id, pid),
              'gathering_participation_conflict',
            );
        r['state'] = 'closed';
        r['version'] = rowVersion(r) + 1;
        r['updatedAt'] = nowWire(i);
      } else
        rehearsalUnsupported();
      row['aggregateVersion'] = rowVersion(row) + 1;
      row['updatedAt'] = nowWire(i);
      return _result(
        i,
        row,
        participation: _p(i)[gatheringParticipationKey(id, i.actorId)],
      );
    },
  );

  Future<Object?> _private(RehearsalInvocation i) async {
    final id = requiredCirclePath(i, 'gatheringId'),
        r = requireRow(_g(i), id, 'gathering_not_found'),
        part = _p(i)[gatheringParticipationKey(id, i.actorId)];
    if (!_organizer(r, i.actorId) && part?['state'] != 'active')
      circleFailure('gathering_active_participation_required');
    return _privateWire(i, r);
  }

  Future<Object?> _public(RehearsalInvocation i) async {
    final r = requireRow(
      _g(i),
      requiredCirclePath(i, 'gatheringId'),
      'gathering_not_found',
    );
    if (r['lifecycleStatus'] == 'draft') circleFailure('gathering_not_found');
    return {
      'card': _card(i, r),
      'audiencePolicy': (r['policySet'] as Map)['audiencePolicy'],
      'admissionPolicy': (r['policySet'] as Map)['admissionPolicy'],
      'disclosurePolicy': cloneRehearsalValue(
        (r['policySet'] as Map)['disclosurePolicy'],
      ),
      'revisions':
          (_plans(i)['${r['gatheringId']}']?['revisions'] as List? ?? const [])
              .map((x) {
                final v = x as Map;
                return {
                  'revisionId': v['revisionId'],
                  'revisionNumber': v['revisionNumber'],
                  'digest': v['revisionDigest'],
                  'materialChange': true,
                  'createdAt': v['committedAt'],
                };
              })
              .toList(),
      if (_p(i)[gatheringParticipationKey(
            '${r['gatheringId']}',
            i.actorId,
          )]?['state'] !=
          null)
        'viewerParticipationState':
            _p(i)[gatheringParticipationKey(
              '${r['gatheringId']}',
              i.actorId,
            )]!['state'],
    };
  }

  Future<Object?> _list(RehearsalInvocation i, String op) async {
    Iterable<Map<String, Object?>> rows = _g(i).values;
    if (op.endsWith('ListMyHostedGatherings'))
      rows = rows.where((r) => _organizer(r, i.actorId));
    else if (op.endsWith('ListGatheringsByHost'))
      rows = rows.where(
        (r) =>
            (r['hostBinding'] as Map)['hostSubjectKind'] ==
                i.query('hostSubjectKind') &&
            (r['hostBinding'] as Map)['hostSubjectId'] ==
                i.query('hostSubjectId') &&
            r['lifecycleStatus'] != 'draft',
      );
    else
      rows = rows.where((r) {
        final refs =
            ((r['purpose'] as Map)['sourceObjectRefs'] as List? ?? const []);
        return r['lifecycleStatus'] != 'draft' &&
            refs.any(
              (x) =>
                  (x as Map)['objectRef'] is Map &&
                  (x['objectRef'] as Map)['objectTypeRef'] ==
                      i.query('sourceObjectTypeRef') &&
                  (x['objectRef'] as Map)['objectId'] ==
                      i.query('sourceObjectId'),
            );
      });
    return pageRows(
      i,
      rows.map((r) => _card(i, r)),
      maximum: 50,
      cursorKey: 'nextCursor',
      hasMore: true,
    );
  }

  Future<Object?> _plan(RehearsalInvocation i) async {
    final id = requiredCirclePath(i, 'gatheringId'),
        r = requireRow(_g(i), id, 'gathering_plan_gathering_unavailable');
    if (!_organizer(r, i.actorId) &&
        _p(i)[gatheringParticipationKey(id, i.actorId)]?['state'] != 'active')
      circleFailure('gathering_plan_permission_denied');
    return cloneRehearsalValue(
      requireRow(_plans(i), id, 'gathering_plan_not_found'),
    );
  }

  Future<Object?> _revisions(RehearsalInvocation i) async {
    final plan = await _plan(i) as Map<String, Object?>;
    return pageRows(
      i,
      (plan['revisions'] as List).cast<Map<String, Object?>>(),
      maximum: 100,
      cursorKey: 'nextCursor',
      hasMore: true,
    );
  }

  bool _organizer(Map<String, Object?> r, String actor) =>
      (r['organizerAssignments'] as List).any(
        (x) => (x as Map)['personaId'] == actor && x['revokedAt'] == null,
      );
  bool _closed(Map<String, Object?> r) =>
      const {'cancelled', 'completed'}.contains(r['lifecycleStatus']);
  int _occupied(RehearsalInvocation i, String id) => _p(i).values
      .where(
        (r) =>
            r['gatheringId'] == id &&
            const {'active', 'invited_pending'}.contains(r['state']),
      )
      .length;
  void _ensureAdmission(
    RehearsalInvocation i,
    Map<String, Object?> r, {
    String? allow,
  }) {
    if (r['lifecycleStatus'] != 'published') circleFailure('invalid_argument');
    if ((r['admissionControl'] as Map)['status'] == 'paused')
      circleFailure('invalid_argument');
    final policy = (r['policySet'] as Map)['admissionPolicy'];
    if (allow != null && policy != allow) circleFailure('invalid_argument');
    if (_occupied(i, '${r['gatheringId']}') >=
        ((r['policySet'] as Map)['capacityPolicy'] as Map)['maxParticipants'])
      circleFailure('gathering_capacity_full');
  }

  Map<String, Object?> _participation(
    RehearsalInvocation i,
    String gid,
    String pid,
    String state,
  ) {
    final now = nowWire(i);
    return {
      'participationId': i.nextId('gp_'),
      'gatheringId': gid,
      'personaId': pid,
      'state': state,
      'version': 1,
      'watchVersion': 0,
      'createdAt': now,
      'updatedAt': now,
    };
  }

  void _newRevision(RehearsalInvocation i, Map<String, Object?> r) {
    final p = _plans(i)['${r['gatheringId']}']!,
        n = ((p['currentRevisionNumber'] as num).toInt()) + 1,
        id = i.nextId('grev_'),
        now = nowWire(i);
    (p['revisions'] as List).add(_revision(id, n, i.actorId, now));
    p['version'] = ((p['version'] as num).toInt()) + 1;
    p['currentRevisionId'] = id;
    p['currentRevisionNumber'] = n;
    p['currentRevisionDigest'] = 'digest:$id';
    p['updatedAt'] = now;
    r['currentGatheringRevisionId'] = id;
    r['currentGatheringRevisionNumber'] = n;
  }

  Map<String, Object?> _revision(String id, int n, String actor, String now) =>
      {
        'revisionId': id,
        'revisionNumber': n,
        'baseRevisionNumber': n - 1,
        'baseRevisionDigest': n == 1 ? 'root' : 'digest:${n - 1}',
        'revisionDigest': 'digest:$id',
        'committedByPersonaId': actor,
        'items': <Object>[],
        'acknowledgementPolicy': {'mode': 'none'},
        'affectedParticipationRefs': <Object>[],
        'committedAt': now,
      };
  Map<String, Object?> _result(
    RehearsalInvocation i,
    Map<String, Object?> r, {
    Map<String, Object?>? participation,
  }) => {
    'gatheringId': r['gatheringId'],
    'aggregateVersion': r['aggregateVersion'],
    'lifecycleStatus': r['lifecycleStatus'],
    if (participation != null) 'participationState': participation['state'],
    if (participation != null) 'participationVersion': participation['version'],
    'currentGatheringRevisionId': r['currentGatheringRevisionId'],
    'currentGatheringRevisionNumber': r['currentGatheringRevisionNumber'],
    if (r['outcomeStatus'] != null) 'outcomeStatus': r['outcomeStatus'],
    'roomBindingStatus': r['roomBindingStatus'],
    'idempotentReplay': false,
  };
  Map<String, Object?> _capacity(
    RehearsalInvocation i,
    Map<String, Object?> r,
  ) {
    final max =
            ((r['policySet'] as Map)['capacityPolicy']
                    as Map)['maxParticipants']
                as int,
        active = _p(i).values
            .where(
              (p) =>
                  p['gatheringId'] == r['gatheringId'] &&
                  p['state'] == 'active',
            )
            .length,
        invited = _p(i).values
            .where(
              (p) =>
                  p['gatheringId'] == r['gatheringId'] &&
                  p['state'] == 'invited_pending',
            )
            .length,
        used = active + invited;
    return {
      'maxParticipants': max,
      'activeSeatCount': active,
      'invitedSeatHoldCount': invited,
      'occupiedSeats': used,
      'remainingSeats': (max - used).clamp(0, max),
      'full': used >= max,
    };
  }

  String _admission(RehearsalInvocation i, Map<String, Object?> r) => _closed(r)
      ? 'closed'
      : (r['admissionControl'] as Map)['status'] == 'paused'
      ? 'paused'
      : (_capacity(i, r)['full'] == true ? 'full' : 'accepting');
  Map<String, Object?> _card(RehearsalInvocation i, Map<String, Object?> r) {
    final purpose = r['purpose'] as Map,
        schedule = r['schedule'] as Map,
        place = r['place'] as Map,
        host = r['hostBinding'] as Map;
    return {
      'gatheringId': r['gatheringId'],
      'aggregateVersion': r['aggregateVersion'],
      'cardDigest': 'card:${r['aggregateVersion']}',
      'host': {
        'hostSubjectKind': host['hostSubjectKind'],
        'hostSubjectId': host['hostSubjectId'],
        'hostDigest': 'host:${host['authorityVersion']}',
      },
      'purpose': {
        'title': purpose['title'] ?? '演练活动',
        'summary': purpose['summary'],
        'topicRefs': purpose['topicRefs'] ?? const <Object>[],
        'requirementRefs': purpose['requirementRefs'] ?? const <Object>[],
        'costNotice': purpose['costNotice'] ?? 'free',
      },
      'schedule': {
        'timezone': schedule['timezone'] ?? 'Asia/Shanghai',
        if (schedule['startAt'] != null) 'startAt': schedule['startAt'],
        if (schedule['endAt'] != null) 'endAt': schedule['endAt'],
      },
      'place': {
        'mode': place['mode'] ?? 'physical',
        if (place['coarsePlaceRef'] != null)
          'coarsePlaceRef': place['coarsePlaceRef'],
        if (place['coarsePlaceLabel'] != null)
          'coarsePlaceLabel': place['coarsePlaceLabel'],
      },
      'capacity': _capacity(i, r),
      'temporal': {'temporalPhase': 'upcoming', 'evaluatedAt': nowWire(i)},
      'admission': {
        'admissionState': _admission(i, r),
        'evaluatedAt': nowWire(i),
      },
      'lifecycleStatus': r['lifecycleStatus'],
      if (r['outcomeStatus'] != null) 'outcomeStatus': r['outcomeStatus'],
      'currentGatheringRevisionId': r['currentGatheringRevisionId'],
      'currentGatheringRevisionNumber': r['currentGatheringRevisionNumber'],
      'updatedAt': r['updatedAt'],
    };
  }

  Map<String, Object?> _privateWire(
    RehearsalInvocation i,
    Map<String, Object?> r,
  ) => {
    ...Map<String, Object?>.from(r)..remove('watchVersion'),
    'capacity': _capacity(i, r),
    'temporal': {'temporalPhase': 'upcoming', 'evaluatedAt': nowWire(i)},
    'admission': {
      'admissionState': _admission(i, r),
      'evaluatedAt': nowWire(i),
    },
  };
  Map<String, Object?> _purpose() => {
    'topicRefs': <Object>[],
    'requirementRefs': <Object>[],
    'sourceObjectRefs': <Object>[],
    'costNotice': 'free',
  };
  Map<String, Object?> _policy() => {
    'audiencePolicy': 'public',
    'admissionPolicy': 'open',
    'capacityPolicy': {'maxParticipants': 20},
    'disclosurePolicy': {
      'timeDisclosure': 'exact',
      'placeDisclosure': 'coarse',
      'rosterDisclosure': 'count_only',
    },
    'applicationQuestions': <Object>[],
    'riskControlPolicyRef': 'rehearsal',
  };
}
