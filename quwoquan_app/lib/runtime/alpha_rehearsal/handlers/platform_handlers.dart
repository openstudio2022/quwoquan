import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';

/// Alpha rehearsal 对平台域能力的诚实声明。任何依赖外部网络或真实媒体
/// transport 的操作都必须 typed fail，不能用占位 token 冒充成功 evidence。
final class RehearsalPlatformCapability {
  const RehearsalPlatformCapability({
    required this.capability,
    required this.supported,
    required this.evidenceKind,
  });

  final String capability;
  final bool supported;
  final String evidenceKind;
}

const rehearsalPlatformCapabilities = <RehearsalPlatformCapability>[
  RehearsalPlatformCapability(
    capability: 'bundle_read',
    supported: true,
    evidenceKind: 'canonical_bundle',
  ),
  RehearsalPlatformCapability(
    capability: 'local_persistence',
    supported: true,
    evidenceKind: 'atomic_rehearsal_store',
  ),
  RehearsalPlatformCapability(
    capability: 'local_realtime_poll',
    supported: true,
    evidenceKind: 'persisted_local_event',
  ),
  RehearsalPlatformCapability(
    capability: 'external_network',
    supported: false,
    evidenceKind: 'unsupported',
  ),
  RehearsalPlatformCapability(
    capability: 'websocket_transport',
    supported: false,
    evidenceKind: 'unsupported',
  ),
  RehearsalPlatformCapability(
    capability: 'rtc_media_transport',
    supported: false,
    evidenceKind: 'unsupported',
  ),
];

final class PlatformRehearsalHandler implements RehearsalObjectHandler {
  const PlatformRehearsalHandler();

  @override
  Future<Object?> handle(RehearsalInvocation invocation) {
    final id = invocation.operation.canonicalOperationId;
    if (id.startsWith('entity.')) return _entity(invocation);
    if (id.startsWith('integration.location.')) return _location(invocation);
    if (id.startsWith('notification.notification.')) {
      return _notification(invocation);
    }
    if (id.startsWith('ops.')) return _ops(invocation);
    if (id.startsWith('search.')) return _search(invocation);
    if (id.startsWith('tag.')) return _tag(invocation);
    if (id.startsWith('realtime.')) return _realtime(invocation);
    if (id.startsWith('rtc.')) return _rtc(invocation);
    return rehearsalUnsupported();
  }

  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) => null;

  Future<Object?> _entity(RehearsalInvocation invocation) async {
    final id = invocation.operation.canonicalOperationId;
    if (id.contains('homepage_review.')) return _homepageReview(invocation);
    final bundle = await OfflineContentBundle.load();
    final homepages = bundle.rows('homepages').map(_projection).toList();
    final homepageId = invocation.path('homepageId');
    if (id.endsWith('.SearchHomepages')) {
      final query = invocation.query('q').trim().toLowerCase();
      final matches = homepages.where((row) {
        final haystack = '${row['displayName']} ${row['summary']}'
            .toLowerCase();
        return query.isEmpty || haystack.contains(query);
      }).toList();
      return _page(invocation, matches, owner: 'entity.homepage.search');
    }
    final homepage = homepages
        .where((row) => row['homepageId'] == homepageId)
        .firstOrNull;
    if (homepage == null) rehearsalNotFound('ENTITY.USER.homepage_not_found');
    return switch (id) {
      'entity.homepage.GetHomepageDetail' ||
      'entity.homepage.GetHomepageIntroduction' ||
      'entity.homepage.GetHomepageShell' ||
      'entity.homepage.GetObjectPageBundle' => cloneRehearsalValue(homepage),
      'entity.homepage.GetHomepageReviewSummary' => _reviewSummary(
        invocation,
        homepageId,
      ),
      'entity.homepage.GetHomepageRelatedGroups' => <String, Object?>{
        'items': homepage['relatedObjects'] ?? const <Object>[],
      },
      _ => rehearsalUnsupported(),
    };
  }

  Future<Object?> _homepageReview(RehearsalInvocation invocation) {
    invocation.requireActor();
    final id = invocation.operation.canonicalOperationId;
    final rows = _records(invocation, 'platform.homepageReviews');
    if (id.endsWith('.ListHomepageReviews')) {
      final homepageId = invocation.query('homepageId').isNotEmpty
          ? invocation.query('homepageId')
          : invocation.path('homepageId');
      return Future.value(
        _page(
          invocation,
          rows.values
              .where(
                (row) =>
                    row['homepageId'] == homepageId &&
                    row['status'] == 'active',
              )
              .toList(),
          owner: 'entity.homepage.review',
        ),
      );
    }
    if (id.endsWith('.GetMyHomepageReview')) {
      final homepageId = invocation.query('homepageId').isNotEmpty
          ? invocation.query('homepageId')
          : '${invocation.body['homepageId'] ?? ''}';
      return Future.value(
        rows.values
            .where(
              (row) =>
                  row['homepageId'] == homepageId &&
                  row['authorPersonaId'] == invocation.actorId &&
                  row['status'] == 'active',
            )
            .firstOrNull,
      );
    }
    return invocation.store.commit(() {
      final mutableRows = _records(invocation, 'platform.homepageReviews');
      if (id.endsWith('.CreateHomepageReview')) {
        final rating = (invocation.body['rating'] as num?)?.toInt() ?? 0;
        final homepageId = '${invocation.body['homepageId'] ?? ''}'.trim();
        if (homepageId.isEmpty || rating < 1 || rating > 5) {
          throw localDomainCloudException(
            'ENTITY.USER.homepage_review_invalid_argument',
          );
        }
        if (mutableRows.values.any(
          (row) =>
              row['homepageId'] == homepageId &&
              row['authorPersonaId'] == invocation.actorId &&
              row['status'] == 'active',
        )) {
          throw localDomainCloudException(
            'ENTITY.USER.homepage_review_already_exists',
          );
        }
        final reviewId = invocation.nextId('review_');
        final now = invocation.now().toUtc().toIso8601String();
        return mutableRows[reviewId] = <String, Object?>{
          'id': reviewId,
          'homepageId': homepageId,
          'authorPersonaId': invocation.actorId,
          'rating': rating,
          'body': invocation.body['body'],
          'tagRefs': invocation.body['tagRefs'] ?? const <Object>[],
          'status': 'active',
          'version': 1,
          'createdAt': now,
          'updatedAt': now,
        };
      }
      final reviewId = invocation.path('reviewId').isNotEmpty
          ? invocation.path('reviewId')
          : '${invocation.body['reviewId'] ?? ''}';
      final row = mutableRows[reviewId];
      if (row == null)
        rehearsalNotFound('ENTITY.USER.homepage_review_not_found');
      if (row['authorPersonaId'] != invocation.actorId) rehearsalUnauthorized();
      if (id.endsWith('.DeleteHomepageReview')) {
        row['status'] = 'deleted';
      } else if (id.endsWith('.UpdateHomepageReview')) {
        final rating = (invocation.body['rating'] as num?)?.toInt() ?? 0;
        if (rating < 1 || rating > 5) {
          throw localDomainCloudException(
            'ENTITY.USER.homepage_review_invalid_argument',
          );
        }
        row['rating'] = rating;
        row['body'] = invocation.body['body'];
        row['tagRefs'] = invocation.body['tagRefs'] ?? const <Object>[];
      } else {
        return rehearsalUnsupported();
      }
      row['version'] = (row['version'] as int) + 1;
      row['updatedAt'] = invocation.now().toUtc().toIso8601String();
      return cloneRehearsalValue(row);
    });
  }

  Object _reviewSummary(RehearsalInvocation invocation, String homepageId) {
    final reviews = _records(invocation, 'platform.homepageReviews').values
        .where(
          (row) => row['homepageId'] == homepageId && row['status'] == 'active',
        )
        .toList();
    final total = reviews.fold<int>(
      0,
      (sum, row) => sum + (row['rating'] as int),
    );
    return <String, Object?>{
      'homepageId': homepageId,
      'reviewCount': reviews.length,
      'averageRating': reviews.isEmpty ? 0.0 : total / reviews.length,
    };
  }

  Future<Object?> _location(RehearsalInvocation invocation) async {
    if (!invocation.operation.canonicalOperationId.endsWith(
      '.SearchLocations',
    )) {
      return rehearsalUnsupported();
    }
    final query = invocation.query('q').trim().toLowerCase();
    if (query.isEmpty) {
      throw localDomainCloudException('INTEGRATION.USER.invalid_argument');
    }
    final bundle = await OfflineContentBundle.load();
    final items = bundle
        .rows('homepages')
        .map(_projection)
        .where((row) {
          return '${row['displayName']} ${row['summary']}'
              .toLowerCase()
              .contains(query);
        })
        .map(
          (row) => <String, Object?>{
            'id': row['homepageId'],
            'name': row['displayName'],
            'latitude': 0.0,
            'longitude': 0.0,
            'address': row['summary'] ?? '',
          },
        )
        .toList();
    final limit = _limit(invocation, maximum: 100);
    return <String, Object?>{'items': items.take(limit).toList()};
  }

  Future<Object?> _notification(RehearsalInvocation invocation) {
    invocation.requireActor();
    final rows = _records(invocation, 'platform.notifications');
    final id = invocation.operation.canonicalOperationId;
    if (id.endsWith('.GetAppMessageUnreadCount')) {
      return Future.value(<String, Object?>{
        'unreadCount': rows.values
            .where(
              (row) =>
                  row['userId'] == invocation.actorId && row['read'] != true,
            )
            .length,
      });
    }
    if (id.endsWith('.ListAppMessages')) {
      final visible =
          rows.values
              .where((row) => row['userId'] == invocation.actorId)
              .toList()
            ..sort(
              (a, b) => '${b['createdAt']}'.compareTo('${a['createdAt']}'),
            );
      return Future.value(
        _page(invocation, visible, owner: 'notification.inbox'),
      );
    }
    final messageId = invocation.path('messageId');
    final row = rows[messageId];
    if (row == null)
      rehearsalNotFound('NOTIFICATION.USER.app_message_not_found');
    if (row['userId'] != invocation.actorId) rehearsalUnauthorized();
    if (id.endsWith('.GetAppMessage'))
      return Future.value(cloneRehearsalValue(row));
    return invocation.store.commit(() {
      final mutableRow = _records(
        invocation,
        'platform.notifications',
      )[messageId]!;
      final now = invocation.now().toUtc().toIso8601String();
      if (id.endsWith('.ReadAppMessage')) {
        mutableRow['read'] = true;
        mutableRow['readAt'] ??= now;
      } else if (id.endsWith('.AckAppMessage')) {
        mutableRow['ackedAt'] ??= now;
      } else {
        return rehearsalUnsupported();
      }
      return cloneRehearsalValue(mutableRow);
    });
  }

  Future<Object?> _ops(RehearsalInvocation invocation) {
    final id = invocation.operation.canonicalOperationId;
    if (id == 'ops.visit_record.RecordVisit') {
      invocation.requireActor();
      return invocation.store.commit(() {
        final type = '${invocation.body['targetType'] ?? ''}';
        final key = '${invocation.body['targetKey'] ?? ''}'.trim();
        if (!const {'page', 'post', 'circle', 'user'}.contains(type) ||
            key.isEmpty) {
          throw localDomainCloudException('OPS.USER.visit_invalid_argument');
        }
        final rows = _records(invocation, 'platform.visits');
        final recordKey = '${invocation.actorId}::$type::$key';
        final existing = rows[recordKey];
        final count = ((existing?['visitCount'] as num?)?.toInt() ?? 0) + 1;
        final result = <String, Object?>{
          'targetType': type,
          'targetKey': key,
          'visitCount': count,
          'occurredAt': invocation.now().toUtc().toIso8601String(),
          'replayed': false,
        };
        rows[recordKey] = result;
        return result;
      });
    }
    if (const {
      'ops.event_record.ReportEventBatch',
      'ops.event_record.ReportRuntimeLogBatch',
      'ops.event_record.ReportStartupEventBatch',
    }.contains(id)) {
      final key = id.endsWith('ReportRuntimeLogBatch') ? 'records' : 'events';
      final values = invocation.body[key];
      if (values is! List || values.isEmpty || !_validLocalEvidence(values)) {
        throw localDomainCloudException(
          id.endsWith('ReportRuntimeLogBatch')
              ? 'OPS.USER.runtime_log_batch_invalid'
              : 'OPS.USER.event_batch_invalid',
        );
      }
      return invocation.store.commit(() {
        _records(invocation, 'platform.reports')[invocation.nextId(
          'report_',
        )] = {
          'kind': key,
          'acceptedCount': values.length,
          'localEvidence': true,
        };
        return <String, Object?>{
          'acceptedCount': values.length,
          'duplicateBatch': false,
        };
      });
    }
    return Future.value(rehearsalUnsupported());
  }

  bool _validLocalEvidence(List<Object?> values) => values.every((item) {
    if (item is! Map) return false;
    final source = item['evidenceSource'] ?? item['source'];
    return source == 'rehearsal_local' || item['runtimeEnv'] == 'alpha';
  });

  Future<Object?> _search(RehearsalInvocation invocation) {
    invocation.requireActor();
    final id = invocation.operation.canonicalOperationId;
    final rows = invocation.store.searchHistory;
    if (id.endsWith('.ListHotQueries')) {
      return Future.value(<String, Object?>{
        'items': const [
          {'query': '三峡', 'heat': 100},
          {'query': '旅行', 'heat': 90},
          {'query': '城市漫步', 'heat': 80},
        ].take(_limit(invocation, maximum: 20)).toList(),
      });
    }
    if (id.endsWith('.ListRecentSearches')) {
      final scope = invocation.query('scope');
      final items =
          rows.values
              .where(
                (row) =>
                    row['actorId'] == invocation.actorId &&
                    (scope.isEmpty || row['scope'] == scope),
              )
              .toList()
            ..sort(
              (a, b) => '${b['updatedAt']}'.compareTo('${a['updatedAt']}'),
            );
      return Future.value(<String, Object?>{'items': items});
    }
    return invocation.store.commit(() {
      final mutableRows = invocation.store.searchHistory;
      if (id.endsWith('.UpsertRecentSearch')) {
        final query = '${invocation.body['query'] ?? ''}'.trim();
        final scope = '${invocation.body['scope'] ?? ''}'.trim();
        if (query.isEmpty || scope.isEmpty)
          throw localDomainCloudException('SEARCH.USER.invalid_argument');
        final entryId = base64Url
            .encode(utf8.encode('$scope\n${query.toLowerCase()}'))
            .replaceAll('=', '');
        return mutableRows[entryId] = <String, Object?>{
          'entryId': entryId,
          'actorId': invocation.actorId,
          'query': query,
          'scope': scope,
          'facet': invocation.body['facet'],
          'updatedAt': invocation.now().toUtc().toIso8601String(),
        };
      }
      if (id.endsWith('.DeleteRecentSearch'))
        mutableRows.remove(invocation.path('entryId'));
      if (id.endsWith('.ClearRecentSearches')) {
        final scope = invocation.query('scope');
        mutableRows.removeWhere(
          (_, row) =>
              row['actorId'] == invocation.actorId &&
              (scope.isEmpty || row['scope'] == scope),
        );
      }
      return <String, Object?>{'status': 'ok'};
    });
  }

  Future<Object?> _tag(RehearsalInvocation invocation) async {
    final id = invocation.operation.canonicalOperationId;
    final bundle = await OfflineContentBundle.load();
    final tags = bundle.rows('tags').map((row) {
      final definition = Map<String, Object?>.from(row['definition']! as Map);
      return <String, Object?>{'tagRef': row['tagRef'], ...definition};
    }).toList();
    if (id.endsWith('.ResolveTag')) {
      final ref = invocation.path('tagRef');
      final row = tags.where((tag) => tag['tagRef'] == ref).firstOrNull;
      if (row == null) rehearsalNotFound('TAG.USER.tag_not_found');
      return row;
    }
    if (id.endsWith('.ValidateTagRefs')) {
      final requested = (invocation.body['tagRefs'] as List? ?? const [])
          .map((e) => '$e')
          .toList();
      final known = tags.map((e) => e['tagRef']).toSet();
      return <String, Object?>{
        'taxonomyReleaseId': bundle.digest,
        'valid': requested.where(known.contains).toList(),
        'invalid': requested.where((ref) => !known.contains(ref)).toList(),
      };
    }
    if (id.endsWith('.ListTagChildren')) {
      final parent = invocation.query('parentTagRef');
      return <String, Object?>{
        'items': tags.where((tag) => tag['parentTagRef'] == parent).toList(),
      };
    }
    return rehearsalUnsupported();
  }

  Future<Object?> _realtime(RehearsalInvocation invocation) async {
    final id = invocation.operation.canonicalOperationId;
    if (id.endsWith('.LongPoll')) {
      invocation.requireActor();
      final cursor = int.tryParse(invocation.query('cursor')) ?? 0;
      final events = invocation.store.events
          .skip(cursor)
          .map(cloneRehearsalValue)
          .toList();
      return <String, Object?>{
        'events': events,
        'nextCursor': '${invocation.store.events.length}',
      };
    }
    // Ticket/WebSocket 都意味着真实 transport；Alpha 不签发可被误认作网络能力的凭据。
    return rehearsalUnsupported();
  }

  Future<Object?> _rtc(RehearsalInvocation invocation) async {
    invocation.requireActor();
    final id = invocation.operation.canonicalOperationId;
    if (id.endsWith('.ListCalls')) {
      final visible = invocation.store.callSessions.values.where((row) {
        final participants = (row['participants'] as List? ?? const []);
        return participants.any(
          (participant) =>
              participant is Map && participant['userId'] == invocation.actorId,
        );
      }).toList();
      return _page(invocation, visible, owner: 'rtc.call.history');
    }
    if (id.endsWith('.GetCall')) {
      final row = invocation.store.callSessions[invocation.path('callId')];
      if (row == null) rehearsalNotFound('RTC.USER.call_not_found');
      _requireCallParticipant(invocation, row);
      return cloneRehearsalValue(row);
    }
    // Initiate/Answer/Join 必须返回媒体凭据，其余控制命令依赖已建立的媒体会话。
    // 无真实媒体 transport 时统一 typed unsupported，且不写入伪造会话。
    return rehearsalUnsupported();
  }

  void _requireCallParticipant(
    RehearsalInvocation invocation,
    Map<String, Object?> row,
  ) {
    final participants = row['participants'] as List? ?? const [];
    if (!participants.any(
      (participant) =>
          participant is Map && participant['userId'] == invocation.actorId,
    )) {
      rehearsalUnauthorized();
    }
  }

  Map<String, Map<String, Object?>> _records(
    RehearsalInvocation invocation,
    String name,
  ) => invocation.store.records.putIfAbsent(
    name,
    () => <String, Map<String, Object?>>{},
  );

  Map<String, Object?> _projection(Map<String, Object?> row) =>
      Map<String, Object?>.from(row['projection']! as Map);

  int _limit(RehearsalInvocation invocation, {required int maximum}) {
    final value = int.tryParse(invocation.query('limit')) ?? 20;
    if (value < 1 || value > maximum)
      throw localDomainCloudException('GATEWAY.USER.invalid_argument');
    return value;
  }

  Map<String, Object?> _page(
    RehearsalInvocation invocation,
    List<Map<String, Object?>> items, {
    required String owner,
  }) {
    final limit = _limit(invocation, maximum: 100);
    final rawCursor = invocation.query('cursor');
    var offset = 0;
    if (rawCursor.isNotEmpty) {
      try {
        final decoded = jsonDecode(
          utf8.decode(base64Url.decode(base64Url.normalize(rawCursor))),
        ) as Map;
        if (decoded['owner'] != owner ||
            decoded['actor'] != invocation.actorId ||
            decoded['offset'] is! int) {
          throw const FormatException();
        }
        offset = decoded['offset'] as int;
      } catch (_) {
        throw localDomainCloudException('GATEWAY.USER.invalid_argument');
      }
    }
    if (offset < 0 || offset > items.length)
      throw localDomainCloudException('GATEWAY.USER.invalid_argument');
    final page = items
        .skip(offset)
        .take(limit)
        .map(cloneRehearsalValue)
        .toList();
    final next = offset + page.length;
    return <String, Object?>{
      'items': page,
      'nextCursor': next < items.length
          ? base64Url
                .encode(
                  utf8.encode(
                    jsonEncode({
                      'owner': owner,
                      'actor': invocation.actorId,
                      'offset': next,
                    }),
                  ),
                )
                .replaceAll('=', '')
          : null,
    };
  }
}
