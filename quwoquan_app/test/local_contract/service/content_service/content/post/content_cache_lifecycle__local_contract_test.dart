import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/content_cache_lifecycle_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';

import '../../../../../support/runtime/cache/content_cache_fixtures.dart';

void main() {
  const digestA =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const digestB =
      'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  final releaseA = ContentActivationIdentity(
    releaseId: 'release-a',
    manifestDigest: digestA,
  );
  final releaseB = ContentActivationIdentity(
    releaseId: 'release-b',
    manifestDigest: digestB,
  );

  AuthSessionState session({
    required String accountId,
    required String personaId,
  }) => AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: accountId,
    activePersonaId: personaId,
    accountState: 'active',
  );

  ContentCacheIsolationIdentity identity(
    ContentActivationIdentity activationIdentity, {
    String accountId = 'account-a',
    String personaId = 'persona-a',
  }) => ContentCacheIsolationIdentity(
    environment: 'alpha',
    audience: ContentReleaseAudience.research,
    accountId: accountId,
    personaId: personaId,
    sourceOwner: 'qwq_data',
    activationIdentity: activationIdentity,
  );

  late PostObjectCacheService postCache;
  late ContentQuerySnapshotStore queryStore;
  late int signedMediaClears;
  late int identityClears;
  late ContentCacheLifecycleCoordinator coordinator;

  setUp(() {
    postCache = PostObjectCacheService();
    queryStore = ContentQuerySnapshotStore(persistToPreferences: false);
    signedMediaClears = 0;
    identityClears = 0;
    coordinator = ContentCacheLifecycleCoordinator(
      postCache: postCache,
      querySnapshotStore: queryStore,
      clearSignedMediaDelivery: () => signedMediaClears += 1,
      clearIsolationIdentity: () => identityClears += 1,
    );
  });

  void seedRebuildableCaches(ContentCacheIsolationIdentity cacheIdentity) {
    postCache.adoptNamespace(cacheIdentity);
    postCache.putProjection(contentCachePostFixture('post-1'));
    queryStore.adoptContentCacheIsolationIdentity(cacheIdentity);
    queryStore.put(
      key: cacheIdentity.isolateQueryKey(
        'surface=discoveryFeed&category=all&cursor=',
      ),
      items: <ContentPostViewData>[contentCachePostFixture('post-1')],
      activationIdentity: cacheIdentity.activationIdentity,
    );
  }

  test('logout、account 与 persona 切换统一清缓存和 signed grant', () {
    var first = session(accountId: 'account-a', personaId: 'persona-a');
    coordinator.handleSessionChange(null, first);

    for (final next in <AuthSessionState>[
      first.copyWith(activePersonaId: 'persona-b'),
      session(accountId: 'account-b', personaId: 'persona-b'),
      const AuthSessionState(status: AuthSessionStatus.guest),
    ]) {
      seedRebuildableCaches(identity(releaseA));
      coordinator.handleSessionChange(first, next);
      expect(postCache.projectionCount, 0);
      expect(queryStore.count, 0);
      first = next;
    }

    expect(signedMediaClears, 3);
    expect(identityClears, 3);
  });

  test('active release tuple 切换清 query/post 与 signed grant，同 tuple 不重复清', () {
    coordinator.handleActivationIdentity(releaseA);
    seedRebuildableCaches(identity(releaseA));

    coordinator.handleActivationIdentity(releaseA);
    expect(postCache.projectionCount, 1);
    expect(queryStore.count, 1);
    expect(signedMediaClears, 0);

    coordinator.handleActivationIdentity(releaseB);
    expect(postCache.projectionCount, 0);
    expect(queryStore.count, 0);
    expect(signedMediaClears, 1);
    expect(identityClears, 1);
  });
}
