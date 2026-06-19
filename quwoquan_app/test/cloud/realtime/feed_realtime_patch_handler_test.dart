import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/feed_realtime_patch_provider.dart';

const String _authedUserId = 'handler-user';
const String _channel = 'moment';

void main() {
  late ProviderContainer container;

  setUp(() async {
    final analytics = AnalyticsService.forTesting(
      mode: AppDataSourceMode.remote,
      eventRepository: MockOpsEventRepository(),
    );
    await analytics.initialize(const AnalyticsConfig());

    final seed = <String, AsyncValue<DiscoveryFeedState>>{
      _channel: AsyncData(
        DiscoveryFeedState(
          items: <PostBaseDto>[_post('p0'), _post('p1')],
          seenItemIds: const <String>['p0', 'p1'],
          feedRequestId: 'frq_handler_1',
        ),
      ),
    };

    container = ProviderContainer(
      overrides: [
        analyticsProvider.overrideWithValue(analytics),
        authSessionControllerProvider.overrideWith(_AuthedSession.new),
        discoveryFeedMapProvider.overrideWith(() => _SeededFeedMap(seed)),
      ],
    );
    addTearDown(container.dispose);
  });

  FeedRealtimePatchHint? hint() =>
      container.read(feedRealtimePatchProvider).hintFor(_channel);

  test('schema 命中 → 路由到 patch 消费者并展示提示', () {
    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'schemaVersion': feedRealtimePatchSchemaVersion,
      'patchId': 'route-1',
      'patchType': 'new_candidate_hint',
      'userId': _authedUserId,
      'feedRequestId': 'frq_handler_1',
      'reasonCode': 'new_candidates_available',
      'affectedCount': 4,
      'emittedAt': '2026-06-18T00:00:00Z',
    });

    expect(hint(), isNotNull);
    expect(hint()!.newCandidateCount, 4);
  });

  test('schema 不符 → 忽略且不落入 chat 处理（不展示、不崩溃）', () {
    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'schemaVersion': 'feed_patch_v999',
      'patchId': 'future-1',
      'patchType': 'new_candidate_hint',
      'userId': _authedUserId,
      'affectedCount': 9,
      'emittedAt': '2026-06-18T00:00:00Z',
    });

    expect(hint(), isNull);
  });

  test('chat 事件不被误判为 feed patch', () {
    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'type': 'ReadReceiptSent',
      'conversationId': 'c1',
    });

    expect(hint(), isNull);
  });

  test('payload 内嵌 schema 也能路由', () {
    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'payload': <String, dynamic>{
        'schemaVersion': feedRealtimePatchSchemaVersion,
        'patchId': 'route-nested-1',
        'patchType': 'refresh_suggestion',
        'userId': _authedUserId,
        'feedRequestId': 'frq_handler_1',
        'reasonCode': 'feed_staleness',
        'emittedAt': '2026-06-18T00:00:00Z',
      },
    });

    expect(hint()!.refreshSuggested, isTrue);
  });
}

PostBaseDto _post(String id) {
  return postBaseDtoFromMap(<String, dynamic>{
    'id': id,
    '_id': id,
    'postId': id,
    'contentType': 'micro',
    'type': 'micro',
    'authorId': 'author-default',
    'subAccountId': 'author-default',
    'displayName': 'fixture',
    'body': 'fixture body $id',
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
  });
}

class _AuthedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    ownerId: 'handler-owner',
    activeSubAccountId: _authedUserId,
    accountState: 'active',
    installId: 'test-install',
  );
}

class _SeededFeedMap extends DiscoveryFeedMapNotifier {
  _SeededFeedMap(this._seed);

  final Map<String, AsyncValue<DiscoveryFeedState>> _seed;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() => _seed;
}
