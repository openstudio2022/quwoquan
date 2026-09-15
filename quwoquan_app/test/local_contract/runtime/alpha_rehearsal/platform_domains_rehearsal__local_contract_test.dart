// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/platform_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/runtime/config/runtime_package_test_hydration.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  installCanonicalOfflineAssetsForTests();
  const handler = PlatformRehearsalHandler();
  late MemoryRehearsalPersistence persistence;
  late AlphaRehearsalStore store;
  var id = 0;

  setUp(() {
    persistence = MemoryRehearsalPersistence();
    store = AlphaRehearsalStore(
      persistence: persistence,
      idFactory: () => '${++id}',
    );
  });

  RehearsalInvocation call(
    String operation, {
    String actor = 'persona-a',
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    Object? body,
    AlphaRehearsalStore? using,
  }) {
    final selected = using ?? store;
    return RehearsalInvocation(
      operation: appCloudOperationContracts[operation]!,
      payload: CloudOperationRequestPayload(
        pathParameters: path,
        queryParameters: query,
        body: body,
      ),
      context: CloudOperationInvocationContext(
        surfaceId: 'alphaRehearsal',
        clientPageId: 'alphaRehearsal',
        actor: CloudOperationActorContext(
          accountId: actor.isEmpty ? null : 'account-a',
          personaId: actor.isEmpty ? null : actor,
          deviceActorId: 'device-a',
        ),
      ),
      store: selected,
      now: () => DateTime.utc(2026, 9, 13, 12),
      nextId: selected.nextId,
    );
  }

  Future<Object?> dispatch(RehearsalInvocation invocation) async {
    await invocation.store.ensureLoaded();
    return handler.handle(invocation);
  }

  test('bundle entity/location/tag 可读，review 分页并重启恢复', () async {
    final homepages = await dispatch(
      call('entity.homepage.SearchHomepages', query: {'q': '三峡', 'limit': '1'}),
    ) as Map;
    expect(homepages['items'], hasLength(1));
    final location = await dispatch(
      call(
        'integration.location.SearchLocations',
        query: {'q': '三峡', 'limit': '5'},
      ),
    ) as Map;
    expect(location['items'], isNotEmpty);
    final tag = await dispatch(
      call('tag.tag_node_view.ResolveTag', path: {'tagRef': 'Entity/地点/住宿/青旅'}),
    ) as Map;
    expect(tag['label'], '青旅');

    for (var rating = 3; rating <= 5; rating++) {
      await dispatch(
        call(
          'entity.homepage_review.CreateHomepageReview',
          actor: 'persona-$rating',
          body: {
            'homepageId': 'hp_9d843480185f1eaed0cefa596e4bf42b',
            'rating': rating,
          },
        ),
      );
    }
    final first = await dispatch(
      call(
        'entity.homepage_review.ListHomepageReviews',
        query: {
          'homepageId': 'hp_9d843480185f1eaed0cefa596e4bf42b',
          'limit': '2',
        },
      ),
    ) as Map;
    expect(first['items'], hasLength(2));
    final restored = AlphaRehearsalStore(persistence: persistence);
    final second = await dispatch(
      call(
        'entity.homepage_review.ListHomepageReviews',
        using: restored,
        query: {
          'homepageId': 'hp_9d843480185f1eaed0cefa596e4bf42b',
          'limit': '2',
          'cursor': first['nextCursor'] as String,
        },
      ),
    ) as Map;
    expect(second['items'], hasLength(1));
  });

  test('notification 分页、权限与 read 状态', () async {
    await store.commit(() {
      final rows = store.records.putIfAbsent(
        'platform.notifications',
        () => {},
      );
      for (var n = 0; n < 3; n++) {
        rows['m$n'] = {
          'messageId': 'm$n',
          'userId': 'persona-a',
          'messageType': 'system',
          'source': 'rehearsal_local',
          'sourceId': 's$n',
          'destination': {'type': 'persona', 'id': 'persona-a'},
          'title': '通知',
          'summary': '本地',
          'target': {
            'targetType': 'page',
            'targetId': 'home',
            'query': <String, Object?>{},
          },
          'read': false,
          'createdAt': '2026-09-13T12:0$n:00.000Z',
        };
      }
    });
    final page = await dispatch(
      call('notification.notification.ListAppMessages', query: {'limit': '2'}),
    ) as Map;
    expect(page['items'], hasLength(2));
    await dispatch(
      call(
        'notification.notification.ReadAppMessage',
        path: {'messageId': 'm0'},
      ),
    );
    final unread = await dispatch(
      call('notification.notification.GetAppMessageUnreadCount'),
    ) as Map;
    expect(unread['unreadCount'], 2);
    await expectLater(
      Future<Object?>.sync(
        () => handler.handle(
          call(
            'notification.notification.GetAppMessage',
            actor: 'persona-b',
            path: {'messageId': 'm0'},
          ),
        ),
      ),
      throwsA(isA<Object>()),
    );
  });

  test('recent、visit、report 可恢复且只采信本地 evidence', () async {
    await dispatch(
      call(
        'search.recent_search_state.UpsertRecentSearch',
        body: {'query': '三峡', 'scope': 'all'},
      ),
    );
    await dispatch(
      call(
        'ops.visit_record.RecordVisit',
        body: {'targetType': 'page', 'targetKey': 'home'},
      ),
    );
    final restored = AlphaRehearsalStore(persistence: persistence);
    final recent = await dispatch(
      call(
        'search.recent_search_state.ListRecentSearches',
        using: restored,
        query: {'scope': 'all'},
      ),
    ) as Map;
    expect(recent['items'], hasLength(1));
    expect(restored.records['platform.visits'], hasLength(1));
    await expectLater(
      Future<Object?>.sync(
        () => handler.handle(
          call(
            'ops.event_record.ReportRuntimeLogBatch',
            body: {
              'records': [
                {'source': 'remote_claim'},
              ],
            },
          ),
        ),
      ),
      throwsA(isA<Object>()),
    );
    final accepted = await dispatch(
      call(
        'ops.event_record.ReportRuntimeLogBatch',
        body: {
          'records': [
            {'evidenceSource': 'rehearsal_local'},
          ],
        },
      ),
    ) as Map;
    expect(accepted['acceptedCount'], 1);
  });

  test('realtime 本地轮询；网络和 RTC media typed unsupported；取消 fence 生效', () async {
    await store.commit(
      () => store.events.add({'eventId': 'local', 'source': 'rehearsal_local'}),
    );
    final poll = await dispatch(
      call('realtime.connection.LongPoll', query: {'cursor': '0'}),
    ) as Map;
    expect(poll['events'], hasLength(1));
    for (final operation in [
      'realtime.connection.IssueConnectionTicket',
      'realtime.connection.WebSocketUpgrade',
      'rtc.call_session.InitiateCall',
      'rtc.call_session.AnswerCall',
    ]) {
      await expectLater(
        handler.handle(
          call(
            operation,
            body: {
              'callType': 'audio',
              'inviteeIds': ['persona-b'],
              'maxParticipants': 2,
            },
          ),
        ),
        throwsA(isA<Object>()),
      );
    }
    expect(store.callSessions, isEmpty);
    final fence = store.captureFence('persona-a');
    await store.resetActor('persona-a');
    expect(fence, throwsA(isA<CloudOperationCancelledException>()));
    expect(
      rehearsalPlatformCapabilities
          .where((item) => !item.supported)
          .map((item) => item.capability),
      containsAll([
        'external_network',
        'websocket_transport',
        'rtc_media_transport',
      ]),
    );
  });
}
