// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart' show compute;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_public_media_delivery.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_bundled.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';

import '../../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:quwoquan_app/service/content_service/content/post/domain/discovery_feed_resident_page_window.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  installCanonicalOfflineAssetsForTests();

  test('scope目录跨顺序消费者仅首次验包且销毁后命中拒绝', () async {
    final assets = _MeasuredFileAssets();
    final scope = OfflineContentReadScope(assets: assets);
    final bundle = await scope.load();
    final creatorId =
        (bundle.rows('creators').first['projection']!
                as Map<String, Object?>)['personaId']!
            as String;
    final postId =
        (bundle.rows('posts').first['projection']!
                as Map<String, Object?>)['postId']!
            as String;
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    final posts = BundledContentPostReader(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    final profiles = BundledProfileQuery(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    final media = BundledPublicMediaDelivery(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    await feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 20,
    );
    await posts.getPost(postId: postId);
    await profiles.getUserHomepageBundle(creatorId);
    await expectLater(
      media.playableSources('media/video/missing.mp4'),
      throwsA(isA<OfflineContentFailure>()),
    );
    expect(assets.manifestReads, 1);
    expect(assets.mediaReads, bundle.rows('media').length);
    expect(identical(bundle, await scope.load()), isTrue);
    scope.dispose();
    await expectLater(scope.load(), throwsA(isA<OfflineContentFailure>()));
    await expectLater(
      posts.getPost(postId: postId),
      throwsA(isA<OfflineContentFailure>()),
    );
    await expectLater(
      profiles.getUserHomepageBundle(creatorId),
      throwsA(isA<OfflineContentFailure>()),
    );
    await expectLater(
      feed.listDiscoveryFeedPage(category: 'recommended', limit: 1),
      throwsA(isA<OfflineContentFailure>()),
    );
    await expectLater(
      media.playableSources('media/video/missing.mp4'),
      throwsA(isA<OfflineContentFailure>()),
    );
  });

  test('scope失败重读与旧generation迟到不污染新目录', () async {
    final assets = _GatedFileAssets();
    final old = OfflineContentReadScope(assets: assets);
    final oldRead = old.load();
    final oldCheck = expectLater(
      oldRead,
      throwsA(isA<OfflineContentFailure>()),
    );
    old.dispose();
    final fresh = OfflineContentReadScope(assets: assets);
    final read = fresh.load();
    assets.gate.complete();
    await oldCheck;
    final bundle = await read;
    old.dispose();
    expect(identical(bundle, await fresh.load()), isTrue);
    expect(assets.manifestReads, 2);
    fresh.dispose();
    final bad = _GatedFileAssets()..corrupt = true;
    bad.gate.complete();
    final retry = OfflineContentReadScope(assets: bad);
    await expectLater(retry.load(), throwsA(isA<OfflineContentFailure>()));
    bad.corrupt = false;
    expect((await retry.load()).digest, offlineContentManifestDigest);
    expect(bad.manifestReads, 2);
    retry.dispose();
  });

  test('计算启动诊断1逐媒体worker内部hash与启动传输', () async {
    final assets = _MeasuredFileAssets();
    final manifest = jsonDecode(
      await File(offlineContentManifestAssetPath).readAsString(),
    ) as Map<String, dynamic>;
    var computeMicros = 0;
    var workerHashMicros = 0;
    var transportMicros = 0;
    var ticks = 0;
    final timer = Timer.periodic(
      const Duration(milliseconds: 10),
      (_) => ticks++,
    );
    final watch = Stopwatch()..start();
    try {
      for (final row
          in (manifest['media'] as List).cast<Map<String, dynamic>>()) {
        final data = await assets.load(row['assetPath'] as String);
        final bytes = data.buffer.asUint8List(
          data.offsetInBytes,
          data.lengthInBytes,
        );
        final outer = Stopwatch()..start();
        final result = await compute(_diagnosticHash, bytes);
        computeMicros += outer.elapsedMicroseconds;
        workerHashMicros += result['micros']! as int;
        expect(result['digest'], row['sha256']);
        outer.reset();
        expect(await compute(_diagnosticLength, bytes), bytes.length);
        transportMicros += outer.elapsedMicroseconds;
      }
    } finally {
      timer.cancel();
      // ignore: avoid_print
      print(
        jsonEncode({
          'diagnostic': 'compute_startup_transfer',
          'elapsedMicros': watch.elapsedMicroseconds,
          'computeRoundtripMicros': computeMicros,
          'workerHashMicros': workerHashMicros,
          'emptyRoundtripMicros': transportMicros,
          'mainTimerTicks': ticks,
          'rssBytes': ProcessInfo.currentRss,
          ...assets.facts,
        }),
      );
    }
  });

  test('计算启动诊断2作者链单次与同adapter重复', () async {
    final assets = _MeasuredFileAssets();
    final raw = jsonDecode(
      await File(offlineContentManifestAssetPath).readAsString(),
    ) as Map<String, dynamic>;
    final id = raw['posts'][0]['projection']['authorId'] as String;
    var calls = 0;
    Future<OfflineContentBundle> load() {
      calls++;
      return OfflineContentBundle.load(assets: assets);
    }

    final profiles = BundledProfileQuery(loadBundle: load);
    final posts = BundledContentPostReader(loadBundle: load);
    for (final stage in [
      'profile_cold',
      'author_posts_cold',
      'author_posts_same_adapter_warm',
    ]) {
      final watch = Stopwatch()..start();
      final before = assets.mediaReads;
      String? failure;
      try {
        if (stage == 'profile_cold') {
          expect(
            (await profiles.getUserHomepageBundle(id)).profile.personaId,
            id,
          );
        } else {
          expect(
            (await posts.listUserPosts(userId: id, limit: 5)).items,
            isNotEmpty,
          );
        }
      } catch (error) {
        failure = error.runtimeType.toString();
        rethrow;
      } finally {
        // ignore: avoid_print
        print(
          jsonEncode({
            'diagnostic': stage,
            'elapsedMicros': watch.elapsedMicroseconds,
            'loadCalls': calls,
            'newMediaReads': assets.mediaReads - before,
            'failure': failure,
            'rssBytes': ProcessInfo.currentRss,
            ...assets.facts,
          }),
        );
      }
    }
  });

  test('同键完整校验single-flight且AssetBundle身份隔离', () async {
    final first = _GatedFileAssets();
    final second = _GatedFileAssets();
    final a = OfflineContentBundle.load(assets: first);
    final b = OfflineContentBundle.load(assets: first);
    final c = OfflineContentBundle.load(assets: second);
    expect(identical(a, b), isTrue);
    expect(identical(a, c), isFalse);
    first.gate.complete();
    second.gate.complete();
    final results = await Future.wait([a, b, c]);
    expect(identical(results[0], results[1]), isTrue);
    expect(identical(results[0], results[2]), isFalse);
    expect(first.manifestReads, 1);
    expect(second.manifestReads, 1);
  });

  test('失败后重新真实校验，旧scope迟到不删除新flight', () async {
    final assets = _GatedFileAssets();
    final old = OfflineContentBundle.load(assets: assets);
    final oldCheck = expectLater(old, throwsA(isA<OfflineContentFailure>()));
    OfflineContentBundle.invalidateSourceScope();
    final fresh = OfflineContentBundle.load(assets: assets);
    assets.gate.complete();
    await oldCheck;
    expect((await fresh).digest, offlineContentManifestDigest);
    expect(assets.manifestReads, 2);
    final bad = _GatedFileAssets()..corrupt = true;
    bad.gate.complete();
    await expectLater(
      OfflineContentBundle.load(assets: bad),
      throwsA(isA<OfflineContentFailure>()),
    );
    bad.corrupt = false;
    expect(
      (await OfflineContentBundle.load(assets: bad)).digest,
      offlineContentManifestDigest,
    );
    expect(bad.manifestReads, 2);
  });

  test('超时flight停止后续媒体读取且不缓存迟到成功', () async {
    final assets = _GatedFileAssets();
    await expectLater(
      OfflineContentBundle.load(assets: assets),
      throwsA(isA<TimeoutException>()),
    );
    assets.gate.complete();
    // 新flight仍执行完整hash，旧flight在manifest读取后检查点停止。
    final fresh = await OfflineContentBundle.load(assets: assets);
    expect(assets.manifestReads, 2);
    expect(assets.mediaReads, fresh.rows('media').length);
  });

  test('共享真实flight单等待者取消不污染其他adapter', () async {
    final assets = _GatedFileAssets();
    Future<OfflineContentBundle> load() =>
        OfflineContentBundle.load(assets: assets);
    final first = BundledContentDiscoveryFeedQuery(loadBundle: load);
    final second = BundledContentDiscoveryFeedQuery(loadBundle: load);
    final signal = CloudOperationCancellationSignal();
    final cancelled = first.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 1,
      cancellation: signal,
    );
    final check = expectLater(
      cancelled,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    final valid = second.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      limit: 1,
    );
    signal.cancel();
    assets.gate.complete();
    await check;
    expect((await valid).items, hasLength(1));
    expect(assets.manifestReads, 1);
  });

  test('性能诊断A真实文件读与hash基线及首次重复完整验证', () async {
    final assets = _MeasuredFileAssets();
    final manifestData = await assets.load(offlineContentManifestAssetPath);
    final manifestBytes = manifestData.buffer.asUint8List(
      manifestData.offsetInBytes,
      manifestData.lengthInBytes,
    );
    final hashClock = Stopwatch()..start();
    expect(
      'sha256:${sha256.convert(manifestBytes)}',
      offlineContentManifestDigest,
    );
    var hashMicros = hashClock.elapsedMicroseconds;
    final decodeClock = Stopwatch()..start();
    final manifest =
        jsonDecode(utf8.decode(manifestBytes)) as Map<String, dynamic>;
    final decodeMicros = decodeClock.elapsedMicroseconds;
    final canonicalClock = Stopwatch()..start();
    final identityBody = Map<String, dynamic>.of(manifest)..remove('bundleId');
    final canonical = canonicalJsonEncode(identityBody);
    final canonicalMicros = canonicalClock.elapsedMicroseconds;
    canonicalClock.reset();
    expect(
      'alpha-${sha256.convert(utf8.encode(canonical))}',
      manifest['bundleId'],
    );
    final identityHashMicros = canonicalClock.elapsedMicroseconds;
    for (final row
        in (manifest['media'] as List).cast<Map<String, dynamic>>()) {
      final data = await assets.load(row['assetPath'] as String);
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      hashClock.reset();
      expect('sha256:${sha256.convert(bytes)}', row['sha256']);
      hashMicros += hashClock.elapsedMicroseconds;
      expect(bytes.length, row['byteLength']);
    }
    // 独立散列基线不在生产load计时内；生产load仍自行读取并完整验证。
    // ignore: avoid_print
    print(
      jsonEncode({
        'diagnostic': 'file_hash_baseline',
        ...assets.facts,
        'hashMicros': hashMicros,
        'manifestDecodeMicros': decodeMicros,
        'manifestCanonicalMicros': canonicalMicros,
        'manifestIdentityHashMicros': identityHashMicros,
        'rssBytes': ProcessInfo.currentRss,
      }),
    );
    for (final stage in ['fresh_bundle', 'repeat_bundle']) {
      assets.reset();
      final watch = Stopwatch()..start();
      final before = ProcessInfo.currentRss;
      final bundle = await OfflineContentBundle.load(assets: assets);
      // ignore: avoid_print
      print(
        jsonEncode({
          'diagnostic': stage,
          'elapsedMicros': watch.elapsedMicroseconds,
          'rssBefore': before,
          'rssAfter': ProcessInfo.currentRss,
          ...assets.facts,
        }),
      );
      expect(bundle.digest, offlineContentManifestDigest);
      expect(assets.manifestReads, 1);
      expect(assets.mediaReads, bundle.rows('media').length);
    }
  });

  test('性能诊断B同isolate三adapter并发真实整包校验', () async {
    final assets = _MeasuredFileAssets();
    // 仅读取路由身份，不建立或预造bundle，不保留媒体字节。
    final raw = jsonDecode(
      await File(offlineContentManifestAssetPath).readAsString(),
    ) as Map<String, dynamic>;
    final postId = raw['posts'][0]['projection']['postId'] as String;
    final personaId = raw['creators'][0]['projection']['personaId'] as String;
    var loads = 0;
    final completions = <String>[];
    final durations = <int>[];
    Future<OfflineContentBundle> load() async {
      loads++;
      final watch = Stopwatch()..start();
      try {
        final bundle = await OfflineContentBundle.load(assets: assets);
        completions.add('passed');
        return bundle;
      } catch (error) {
        completions.add(error.runtimeType.toString());
        rethrow;
      } finally {
        durations.add(watch.elapsedMicroseconds);
      }
    }

    final feed = BundledContentDiscoveryFeedQuery(loadBundle: load);
    final posts = BundledContentPostReader(loadBundle: load);
    final profiles = BundledProfileQuery(loadBundle: load);
    final before = ProcessInfo.currentRss;
    try {
      await Future.wait<Object?>([
        feed.listDiscoveryFeedPage(
          category: 'recommended',
          channelId: 'recommend',
          limit: 20,
        ),
        posts.getPost(postId: postId),
        profiles.getPersonaProfile(personaId),
      ]);
    } finally {
      // ignore: avoid_print
      print(
        jsonEncode({
          'diagnostic': 'three_adapters_same_isolate',
          'loads': loads,
          'completions': completions,
          'durationsMicros': durations,
          'rssBefore': before,
          'rssAfter': ProcessInfo.currentRss,
          ...assets.facts,
        }),
      );
    }
    expect(loads, 3);
    expect(assets.manifestReads, 1);
    expect(assets.mediaReads, (raw['media'] as List).length);
  });
  test('真实频道跨20分页读取完整终止，premium图片和视频均可达', () async {
    final bundle = await OfflineContentBundle.load();
    final feed = BundledContentDiscoveryFeedQuery(
      loadBundle: () async => bundle,
    );
    final detail = BundledContentPostReader(loadBundle: () async => bundle);
    for (final channel in ['recommend', 'premium']) {
      final expected =
          (bundle
                      .rows('channels')
                      .singleWhere(
                        (row) => row['channelId'] == channel,
                      )['orderedPostIds']!
                  as List)
              .cast<String>();
      final ids = <String>[];
      final cursors = <String>{};
      final types = <String>{};
      String? cursor;
      var pages = 0;
      do {
        final page = await feed.listDiscoveryFeedPage(
          category: channel == 'premium' ? 'video' : 'recommended',
          channelId: channel,
          limit: homeFeedPageItemLimit,
          cursor: cursor,
        );
        expect(page.activationIdentity, isNull);
        expect(page.outcome, ContentFeedOutcome.content);
        expect(page.items, isNotEmpty);
        if (pages == 0) {
          expect(page.items, hasLength(homeFeedPageItemLimit));
          expect(page.nextCursor, isNotNull);
        }
        for (final post in page.items) {
          expect(ids, isNot(contains(post.id)));
          ids.add(post.id);
          types.add(post.type);
          final payload = await detail.getPost(postId: post.id);
          expect(payload.post.id, post.id);
          expect(payload.post.type, post.type);
        }
        pages++;
        cursor = page.nextCursor;
        if (cursor != null) expect(cursors.add(cursor), isTrue);
        expect(pages, lessThanOrEqualTo(expected.length));
      } while (cursor != null);
      expect(pages, greaterThanOrEqualTo(2));
      expect(ids.length, greaterThan(homeFeedPageItemLimit));
      expect(ids, orderedEquals(expected));
      if (channel == 'premium') expect(types, {'image', 'video'});
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
    final selected =
        (bundle
                    .rows('channels')
                    .singleWhere(
                      (row) => row['channelId'] == 'recommend',
                    )['orderedPostIds']!
                as List)
            .cast<String>();
    expect(ids, selected.toSet());
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

Map<String, Object> _diagnosticHash(Uint8List bytes) {
  final watch = Stopwatch()..start();
  final digest = 'sha256:${sha256.convert(bytes)}';
  return {'digest': digest, 'micros': watch.elapsedMicroseconds};
}

int _diagnosticLength(Uint8List bytes) => bytes.length;

final class _GatedFileAssets extends _MeasuredFileAssets {
  final gate = Completer<void>();
  bool corrupt = false;

  @override
  Future<ByteData> load(String key) async {
    if (key == offlineContentManifestAssetPath) await gate.future;
    final data = await super.load(key);
    if (corrupt && key == offlineContentManifestAssetPath) return ByteData(1);
    return data;
  }
}

/// 只记录真实文件读取，不缓存字节，不替换生产时钟或hash。
class _MeasuredFileAssets extends AssetBundle {
  int manifestReads = 0;
  int mediaReads = 0;
  int byteCount = 0;
  int manifestReadMicros = 0;
  int mediaReadMicros = 0;

  Map<String, int> get facts => {
    'manifestReads': manifestReads,
    'mediaReads': mediaReads,
    'bytesRead': byteCount,
    'manifestReadMicros': manifestReadMicros,
    'mediaReadMicros': mediaReadMicros,
  };

  void reset() {
    manifestReads = mediaReads = byteCount = manifestReadMicros =
        mediaReadMicros = 0;
  }

  @override
  Future<ByteData> load(String key) async {
    final watch = Stopwatch()..start();
    final bytes = await File(key).readAsBytes();
    final micros = watch.elapsedMicroseconds;
    byteCount += bytes.length;
    if (key == offlineContentManifestAssetPath) {
      manifestReads++;
      manifestReadMicros += micros;
    } else {
      mediaReads++;
      mediaReadMicros += micros;
    }
    return ByteData.sublistView(bytes);
  }
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
