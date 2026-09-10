// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_bundled.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('canonical 制品全部媒体与投影可读取，premium 不扩为普通视频', () async {
    final bundle = await OfflineContentBundle.load();
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: () async => bundle,
    );
    final detail = BundledContentPostReader(loadBundle: () async => bundle);
    final recommendation = await feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 20,
    );
    expect(recommendation.items, hasLength(bundle.rows('posts').length));
    expect(recommendation.activationIdentity, isNull);
    expect(recommendation.nextCursor, isNull);
    final premium = await feed.listDiscoveryFeedPage(
      category: 'video',
      channelId: 'premium',
      limit: 20,
    );
    expect(
      premium.items.map((post) => post.id),
      bundle
          .rows('channels')
          .singleWhere(
            (row) => row['channelId'] == 'premium',
          )['orderedPostIds'],
    );
    for (final post in recommendation.items) {
      final payload = await detail.getPost(postId: post.id);
      expect(payload, isNotNull);
    }
  });

  test('分页不重复、终止明确、跨查询游标拒绝，空频道不伪造服务缺席', () async {
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: OfflineContentBundle.load,
    );
    final ids = <String>{};
    String? cursor;
    do {
      final page = await feed.listDiscoveryFeedPage(
        category: 'recommended',
        channelId: 'recommend',
        limit: 1,
        cursor: cursor,
      );
      expect(page.items, hasLength(1));
      expect(ids.add(page.items.single.id), isTrue);
      cursor = page.nextCursor;
      if (cursor != null) {
        await expectLater(
          feed.listDiscoveryFeedPage(
            category: 'video',
            channelId: 'premium',
            limit: 1,
            cursor: cursor,
          ),
          throwsA(isA<OfflineContentFailure>()),
        );
      }
    } while (cursor != null);
    final bundle = await OfflineContentBundle.load();
    expect(ids, hasLength(bundle.rows('posts').length));
    final empty = await feed.listDiscoveryFeedPage(
      category: 'work',
      channelId: 'campus',
      limit: 1,
    );
    expect(empty.outcome, ContentFeedOutcome.empty);
    expect(empty.emptyReason, ContentFeedEmptyReason.noEligibleContent);
    expect(empty.activationIdentity, isNull);
  });

  test('creator 主页与作者作品使用同一快照，公开头像保留交付绑定', () async {
    final bundle = await OfflineContentBundle.load();
    final profiles = BundledProfileQuery(loadBundle: () async => bundle);
    final posts = BundledContentPostReader(loadBundle: () async => bundle);
    for (final row in bundle.rows('creators')) {
      final creator = PersonaProfileView.fromWire(
        row['projection']! as Map<String, Object?>,
      );
      final homepage = await profiles.getUserHomepageBundle(creator.personaId);
      final profile = await profiles.getPersonaProfile(creator.personaId);
      expect(homepage.profile.displayName, creator.displayName);
      expect(homepage.profile.avatarAssetId, creator.avatarAssetId);
      expect(homepage.profile.avatarAccessMode, creator.avatarAccessMode);
      expect(profile.personaId, homepage.profile.personaId);
      expect(homepage.viewerContext.isGuest, isTrue);
      expect(homepage.relationshipCapability, isNull);
      expect(homepage.cacheVersion, bundle.digest);
      final expected = bundle
          .rows('posts')
          .map(
            (row) => ContentPostProjection.fromWire(
              row['projection']! as Map<String, Object?>,
            ),
          )
          .where((post) => post.authorId == creator.personaId)
          .toList();
      final ids = <String>{};
      String? cursor;
      do {
        final page = await posts.listUserPosts(
          userId: creator.personaId,
          limit: 1,
          cursor: cursor,
        );
        for (final post in page.items) {
          expect(ids.add(post.id), isTrue);
        }
        cursor = page.nextCursor;
        if (cursor != null) {
          await expectLater(
            posts.listUserPosts(
              userId: 'other-creator',
              limit: 1,
              cursor: cursor,
            ),
            throwsA(isA<OfflineContentFailure>()),
          );
        }
      } while (cursor != null);
      expect(ids, expected.map((post) => post.postId).toSet());
      expect(homepage.stats.postCount, expected.length);
      for (final type in expected.map((post) => post.contentType).toSet()) {
        final page = await posts.listUserPosts(
          userId: creator.personaId,
          type: type,
        );
        expect(page.items.every((post) => post.type == type), isTrue);
      }
    }
  });

  test('creator 私域与 persona 管理不伪造身份或空列表', () async {
    final profiles = BundledProfileQuery(loadBundle: OfflineContentBundle.load);
    final posts = BundledContentPostReader(
      loadBundle: OfflineContentBundle.load,
    );
    for (final request in <Future<Object?>>[
      profiles.getUserProfile('me'),
      profiles.listPersonas(),
      profiles.getActivePersonaContext(),
      profiles.getPersonaManagementSummary(),
      profiles.getPersonaLifecycleGuard('creator'),
      profiles.searchSocialRelations(query: 'creator'),
      posts.listUserPosts(userId: 'me'),
      posts.listUserPosts(userId: 'creator', visibility: 'private'),
    ]) {
      await expectLater(
        request,
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.kind,
            'kind',
            RuntimeFailureKind.unsupported,
          ),
        ),
      );
    }
  });

  test('冻结保持原始 nested JSON 值和 list 类型且不可改写', () async {
    final raw = jsonDecode(
      await rootBundle.loadString(offlineContentManifestAssetPath),
    ) as Map<String, Object?>;
    final bundle = await OfflineContentBundle.load();
    expect(bundle.document, raw);
    expect(bundle.media.byAssetId, hasLength(bundle.rows('media').length));
    expect(
      bundle.media.byAssetId.values.fold<int>(
        0,
        (sum, asset) => sum + asset.byteLength,
      ),
      (raw['counts']! as Map<String, Object?>)['mediaBytes'],
    );
    final configuration =
        bundle.document['configuration']! as Map<String, Object?>;
    final content = configuration['content']! as Map<String, Object?>;
    final gray = content['gray_release']! as Map<String, Object?>;
    expect(gray['canary_matrix'], isA<List<Object?>>());
    expect(
      () => (gray['canary_matrix']! as List).add('invalid'),
      throwsUnsupportedError,
    );
    expect(() => content['gray_release'] = null, throwsUnsupportedError);
  });

  test('已取消或已过期请求不开始读取 bundle', () async {
    var loads = 0;
    Future<OfflineContentBundle> load() {
      loads += 1;
      throw StateError('不应开始读取');
    }

    final feed = BundledContentDiscoveryFeedQuery(loadBundle: load);
    final detail = BundledContentPostReader(loadBundle: load);
    final cancellation = CloudOperationCancellationSignal()..cancel();
    final expired = DateTime.now().subtract(const Duration(seconds: 1));
    await expectLater(
      feed.listDiscoveryFeedPage(
        category: 'recommended',
        limit: 1,
        cancellation: cancellation,
      ),
      throwsA(isA<CloudOperationCancelledException>()),
    );
    await expectLater(
      detail.getPost(postId: 'unknown', cancellation: cancellation),
      throwsA(isA<CloudOperationCancelledException>()),
    );
    await expectLater(
      feed.listDiscoveryFeedPage(
        category: 'recommended',
        limit: 1,
        deadlineAt: expired,
      ),
      throwsA(isA<TimeoutException>()),
    );
    await expectLater(
      detail.getPost(postId: 'unknown', deadlineAt: expired),
      throwsA(isA<TimeoutException>()),
    );
    expect(loads, 0);
  });

  test('加载期间取消和 deadline 有界终止，不取消同 adapter 的其他读取', () async {
    final loading = Completer<OfflineContentBundle>();
    var loads = 0;
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: () {
        loads += 1;
        return loading.future;
      },
    );
    final detail = BundledContentPostReader(loadBundle: () => loading.future);
    final cancellation = CloudOperationCancellationSignal();
    final cancelledFeed = feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 1,
      cancellation: cancellation,
    );
    final cancelledDetail = detail.getPost(
      postId: 'unknown',
      cancellation: cancellation,
    );
    final feedExpectation = expectLater(
      cancelledFeed,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    final detailExpectation = expectLater(
      cancelledDetail,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    final surviving = feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 1,
    );
    cancellation.cancel();
    await Future.wait([feedExpectation, detailExpectation]);
    final deadline = DateTime.now().add(const Duration(milliseconds: 20));
    await Future.wait([
      expectLater(
        feed.listDiscoveryFeedPage(
          category: 'recommended',
          limit: 1,
          deadlineAt: deadline,
        ),
        throwsA(isA<TimeoutException>()),
      ),
      expectLater(
        detail.getPost(postId: 'unknown', deadlineAt: deadline),
        throwsA(isA<TimeoutException>()),
      ),
    ]);
    loading.complete(await OfflineContentBundle.load());
    expect((await surviving).items, hasLength(1));
    expect(loads, 1);
  });

  testWidgets('未指定 deadline 也受 6 秒总读取预算约束', (tester) async {
    final loading = Completer<OfflineContentBundle>();
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: () => loading.future,
    );
    final detail = BundledContentPostReader(loadBundle: () => loading.future);
    final feedExpectation = expectLater(
      feed.listDiscoveryFeedPage(
        category: 'recommended',
        channelId: 'recommend',
        limit: 1,
      ),
      throwsA(isA<TimeoutException>()),
    );
    final detailExpectation = expectLater(
      detail.getPost(postId: 'unknown'),
      throwsA(isA<TimeoutException>()),
    );
    await tester.pump(const Duration(seconds: 6));
    await Future.wait([feedExpectation, detailExpectation]);
    loading.completeError(const OfflineContentFailure('bundle_unavailable'));
    await tester.pump();
  });

  test('不支持的个性化读取返回 typed unavailable，不伪装空页', () async {
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: OfflineContentBundle.load,
    );
    for (final request in [
      feed.listDiscoveryFeedPage(category: 'following', limit: 1),
      feed.listDiscoveryFeedPage(
        category: 'recommended',
        sort: 'latest',
        limit: 1,
      ),
      feed.listDiscoveryFeedPage(
        category: 'recommended',
        subCategory: 'private',
        limit: 1,
      ),
    ]) {
      await expectLater(
        request,
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.kind,
            'kind',
            RuntimeFailureKind.unsupported,
          ),
        ),
      );
    }
  });

  test('失败后重试重新读取，不缓存失败或回退其他 source', () async {
    var loads = 0;
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: () async {
        if (++loads == 1) {
          throw const OfflineContentFailure('bundle_unavailable');
        }
        return OfflineContentBundle.load();
      },
    );
    await expectLater(
      feed.listDiscoveryFeedPage(category: 'recommended', limit: 1),
      throwsA(isA<OfflineContentFailure>()),
    );
    expect(
      (await feed.listDiscoveryFeedPage(
        category: 'recommended',
        channelId: 'recommend',
        limit: 1,
      )).items,
      hasLength(1),
    );
    expect(loads, 2);
  });

  test('配置 digest 与实际配置不一致时拒绝读取', () async {
    final raw = jsonDecode(
      await rootBundle.loadString(offlineContentManifestAssetPath),
    ) as Map<String, Object?>;
    raw['configurationDigest'] = 'sha256:${'0' * 64}';
    final body = Map<String, Object?>.of(raw)..remove('bundleId');
    raw['bundleId'] =
        'alpha-${sha256.convert(utf8.encode(canonicalJsonEncode(body)))}';
    final bytes = Uint8List.fromList(utf8.encode(canonicalJsonEncode(raw)));
    await expectLater(
      OfflineContentBundle.load(
        assets: _ManifestBundle(bytes),
        expectedDigest: 'sha256:${sha256.convert(bytes)}',
      ),
      throwsA(
        isA<OfflineContentFailure>().having(
          (error) => error.reason,
          'reason',
          'bundle_configuration_integrity_invalid',
        ),
      ),
    );
  });

  test('快照摘要或任何媒体损坏均拒绝整个读取', () async {
    try {
      await OfflineContentBundle.load(expectedDigest: 'sha256:${'0' * 64}');
      fail('坏摘要不能发布快照');
    } catch (error) {
      expect(error, isA<OfflineContentFailure>());
      expect(
        (error as OfflineContentFailure).reason,
        'bundle_manifest_integrity_invalid',
      );
    }
    try {
      await OfflineContentBundle.load(assets: _CorruptMediaBundle());
      fail('坏媒体不能发布快照');
    } catch (error) {
      expect(error, isA<OfflineContentFailure>());
      expect(
        (error as OfflineContentFailure).reason,
        'bundle_media_integrity_invalid',
      );
    }
  });
}

final class _ManifestBundle extends CachingAssetBundle {
  _ManifestBundle(this.bytes);
  final Uint8List bytes;

  @override
  Future<ByteData> load(String key) async =>
      key == offlineContentManifestAssetPath
      ? ByteData.sublistView(bytes)
      : rootBundle.load(key);
}

final class _CorruptMediaBundle extends CachingAssetBundle {
  @override
  Future<ByteData> load(String key) async =>
      key.startsWith('assets/content/alpha/media/')
      ? ByteData(1)
      : rootBundle.load(key);
}
