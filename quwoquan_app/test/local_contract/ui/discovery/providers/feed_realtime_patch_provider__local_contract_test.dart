// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/realtime-feed-baseline/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/content/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/content/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/content/content/post/application/feed_realtime_patch_provider.dart';

import '../../../../support/recording_app_telemetry_recorder.dart';

const String _authedUserId = 'test-persona';
const String _channel = 'moment';
const String _policyA =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const String _policyB =
    'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  late RecordingAppTelemetryRecorder ops;
  late AnalyticsService analytics;

  setUp(() async {
    ops = RecordingAppTelemetryRecorder();
    analytics = AnalyticsService.forTesting(telemetryReporter: ops);
    await analytics.initialize(const AnalyticsConfig());
  });

  ProviderContainer buildContainer({
    required List<ContentPostViewData> items,
    String feedRequestId = 'frq_test_1',
    String? policyDigest = _policyA,
    bool authenticated = true,
  }) {
    final seed = <String, AsyncValue<DiscoveryFeedState>>{
      _channel: AsyncData(
        DiscoveryFeedState(
          items: items,
          seenItemIds: items.map((e) => e.id).toList(growable: false),
          feedRequestId: feedRequestId,
          policyDigest: policyDigest,
        ),
      ),
    };
    final container = ProviderContainer(
      overrides: [
        analyticsProvider.overrideWithValue(analytics),
        authSessionControllerProvider.overrideWith(
          authenticated ? _AuthedSession.new : _GuestSession.new,
        ),
        discoveryFeedMapProvider.overrideWith(() => _SeededFeedMap(seed)),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  List<String> currentItemIds(ProviderContainer container) {
    final value = container.read(discoveryFeedMapProvider)[_channel]?.value;
    return value?.items.map((e) => e.id).toList(growable: false) ??
        const <String>[];
  }

  List<RecordedAppTelemetry> eventsNamed(String name) => ops.recorded
      .where(
        (event) =>
            event.action == name || event.extensions['operationId'] == name,
      )
      .toList();

  group('negative_feedback_removal · 不打断阅读位置', () {
    test('post 维度：仅移除视口之外的目标项，视口内目标暂缓', () {
      final items = _posts(5);
      final container = buildContainer(items: items);
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      // 视口 = p0..p2（floor=2）；p1 在视口内、p4 在视口之外。
      notifier.setPostMounted('p0', mounted: true);
      notifier.setPostMounted('p1', mounted: true);
      notifier.setPostMounted('p2', mounted: true);

      notifier.applyPatch(
        _patch(
          patchId: 'patch-remove-post',
          type: FeedRealtimePatchType.negativeFeedbackRemoval,
          targetPostIds: const <String>['p1', 'p4'],
          removalDimension: FeedPatchRemovalDimension.post,
        ),
      );

      // p4（视口外）被移除；p1（视口内）保留，阅读位置不受影响。
      expect(currentItemIds(container), <String>['p0', 'p1', 'p2', 'p3']);
    });

    test('author 维度：移除视口之外同作者项，保留视口内与他作者项', () {
      final items = <ContentPostViewData>[
        _post('p0', authorId: 'authorA'),
        _post('p1', authorId: 'authorA'),
        _post('p2', authorId: 'authorB'),
        _post('p3', authorId: 'authorA'),
        _post('p4', authorId: 'authorA'),
      ];
      final container = buildContainer(items: items);
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      // 视口 = p0..p1（floor=1）。
      notifier.setPostMounted('p0', mounted: true);
      notifier.setPostMounted('p1', mounted: true);

      notifier.applyPatch(
        _patch(
          patchId: 'patch-remove-author',
          type: FeedRealtimePatchType.negativeFeedbackRemoval,
          removalDimension: FeedPatchRemovalDimension.author,
          removalDimensionValue: 'authorA',
        ),
      );

      // 仅 p3/p4（视口外 authorA）移除；p0/p1（视口内）与 p2（authorB）保留。
      expect(currentItemIds(container), <String>['p0', 'p1', 'p2']);
    });

    test('无任何已挂载项时保守暂缓（不误删可能可见的项）', () {
      final items = _posts(3);
      final container = buildContainer(items: items);
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      // 不上报任何视口项 → floor < 0 → 全部暂缓。
      notifier.applyPatch(
        _patch(
          patchId: 'patch-remove-unknown-viewport',
          type: FeedRealtimePatchType.negativeFeedbackRemoval,
          targetPostIds: const <String>['p0', 'p1', 'p2'],
          removalDimension: FeedPatchRemovalDimension.post,
        ),
      );

      expect(currentItemIds(container), <String>['p0', 'p1', 'p2']);
    });
  });

  group('new_candidate_hint / refresh_suggestion · 仅展示入口', () {
    test('new_candidate_hint 累积计数、不插入内容、不改变顺序', () {
      final items = _posts(2);
      final container = buildContainer(items: items);
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'hint-1',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 5,
        ),
      );

      final hint = container.read(feedRealtimePatchProvider).hintFor(_channel);
      expect(hint, isNotNull);
      expect(hint!.newCandidateCount, 5);
      expect(hint.hasUpdate, isTrue);
      expect(hint.policyDigest, _policyA);
      // 不插入、不跳位：feed 内容与顺序保持不变。
      expect(currentItemIds(container), <String>['p0', 'p1']);
    });

    test('refresh_suggestion 仅置刷新提示，不带计数', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'refresh-1',
          type: FeedRealtimePatchType.refreshSuggestion,
        ),
      );

      final hint = container.read(feedRealtimePatchProvider).hintFor(_channel);
      expect(hint!.refreshSuggested, isTrue);
      expect(hint.newCandidateCount, 0);
      expect(hint.hasUpdate, isTrue);
      expect(currentItemIds(container), <String>['p0', 'p1']);
    });

    test('latest patch 未提供 policyDigest 时清空 hint 归因而不沿用', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'hint-with-policy',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 1,
        ),
      );
      expect(
        container
            .read(feedRealtimePatchProvider)
            .hintFor(_channel)!
            .policyDigest,
        _policyA,
      );

      notifier.applyPatch(
        _patch(
          patchId: 'hint-without-policy',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 1,
          policyDigest: null,
        ),
      );
      final hint = container.read(feedRealtimePatchProvider).hintFor(_channel)!;
      expect(hint.newCandidateCount, 2);
      expect(
        hint.policyDigest,
        isNull,
        reason:
            'null means source omitted; it must not fallback to prior digest',
      );
    });
  });

  group('幂等去重 / 对齐 / 鉴权', () {
    test('provider boundary rejects a non-canonical policyDigest', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      expect(
        () => notifier.applyPatch(
          _patch(
            patchId: 'invalid-policy-1',
            type: FeedRealtimePatchType.newCandidateHint,
            policyDigest: '',
          ),
        ),
        throwsFormatException,
      );
      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
    });

    test('patchId 去重：同一 patchId 重复到达只生效一次', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      final patch = _patch(
        patchId: 'dup-1',
        type: FeedRealtimePatchType.newCandidateHint,
        affectedCount: 3,
      );
      notifier.applyPatch(patch);
      notifier.applyPatch(patch);

      expect(
        container
            .read(feedRealtimePatchProvider)
            .hintFor(_channel)!
            .newCandidateCount,
        3,
      );
    });

    test('feedRequestId 不匹配则忽略（不剔除、不展示）', () {
      final container = buildContainer(
        items: _posts(3),
        feedRequestId: 'frq_current',
      );
      final notifier = container.read(feedRealtimePatchProvider.notifier);
      notifier.setPostMounted('p0', mounted: true);

      notifier.applyPatch(
        _patch(
          patchId: 'stale-1',
          type: FeedRealtimePatchType.negativeFeedbackRemoval,
          feedRequestId: 'frq_stale',
          targetPostIds: const <String>['p2'],
          removalDimension: FeedPatchRemovalDimension.post,
        ),
      );

      expect(currentItemIds(container), <String>['p0', 'p1', 'p2']);
      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
    });

    test('policyDigest 不匹配当前 channel feed 则忽略', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'stale-policy-1',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 2,
          policyDigest: _policyB,
        ),
      );

      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
      expect(eventsNamed('feed_patch_misaligned'), hasLength(1));
    });

    test('游客不消费 patch（鉴权门拦截）', () {
      final container = buildContainer(items: _posts(2), authenticated: false);
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'guest-1',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 9,
        ),
      );

      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
    });

    test('patch.userId 与当前用户不一致则忽略', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'other-user-1',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 4,
          userId: 'someone-else',
        ),
      );

      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
    });
  });

  group('反馈回流 · 统一埋点出口', () {
    test('收到 + 展示 记录到 analytics', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);

      notifier.applyPatch(
        _patch(
          patchId: 'fb-1',
          type: FeedRealtimePatchType.newCandidateHint,
          affectedCount: 2,
        ),
      );

      expect(eventsNamed('feed_patch_received'), hasLength(1));
      expect(eventsNamed('feed_patch_displayed'), hasLength(1));
      final received = eventsNamed('feed_patch_received').first;
      expect(received.eventType, 'product_action');
      expect(received.extensions.containsKey('patchId'), isFalse);
    });

    test('点击刷新记录并清除提示', () {
      final container = buildContainer(items: _posts(2));
      final notifier = container.read(feedRealtimePatchProvider.notifier);
      notifier.applyPatch(
        _patch(
          patchId: 'fb-refresh',
          type: FeedRealtimePatchType.refreshSuggestion,
        ),
      );

      notifier.acknowledgeRefresh(_channel);

      expect(eventsNamed('feed_patch_refresh_clicked'), hasLength(1));
      expect(
        container.read(feedRealtimePatchProvider).hintFor(_channel),
        isNull,
      );
    });
  });
}

// ── 测试夹具 ──────────────────────────────────────────────────────────────

List<ContentPostViewData> _posts(int count) =>
    List<ContentPostViewData>.generate(count, (i) => _post('p$i'));

ContentPostViewData _post(String id, {String authorId = 'author-default'}) {
  return contentPostViewDataFromReadModelMap(<String, dynamic>{
    'id': id,
    '_id': id,
    'postId': id,
    'contentType': 'micro',
    'type': 'micro',
    'authorId': authorId,
    'personaId': authorId,
    'displayName': 'fixture',
    'body': 'fixture body $id',
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
  });
}

FeedRealtimePatch _patch({
  required String patchId,
  required FeedRealtimePatchType type,
  String userId = _authedUserId,
  String feedRequestId = 'frq_test_1',
  List<String> targetPostIds = const <String>[],
  FeedPatchRemovalDimension? removalDimension,
  String? removalDimensionValue,
  int affectedCount = 0,
  String? policyDigest = _policyA,
}) {
  return FeedRealtimePatch(
    patchId: patchId,
    patchType: type,
    userId: userId,
    feedRequestId: feedRequestId,
    channelId: null,
    targetPostIds: targetPostIds,
    reasonCode: FeedPatchReasonCode.negativeDislike,
    removalDimension: removalDimension,
    removalDimensionValue: removalDimensionValue,
    affectedCount: affectedCount,
    policyDigest: policyDigest,
    safeToApplyWhileViewing: true,
    emittedAt: '2026-06-18T00:00:00Z',
  );
}

class _AuthedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    refreshToken: 'test-refresh-token',
    ownerId: 'test-owner',
    activePersonaId: _authedUserId,
    accountState: 'active',
    installId: 'test-install',
  );
}

class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.guest,
    installId: 'test',
  );
}

class _SeededFeedMap extends DiscoveryFeedMapNotifier {
  _SeededFeedMap(this._seed);

  final Map<String, AsyncValue<DiscoveryFeedState>> _seed;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() => _seed;
}
