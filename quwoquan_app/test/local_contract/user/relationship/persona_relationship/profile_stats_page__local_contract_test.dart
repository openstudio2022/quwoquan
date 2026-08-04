import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/user/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

class _FakeHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;
  @override
  Duration? connectionTimeout;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;

  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}

  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}

  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}

  @override
  set authenticateProxy(
    Future<bool> Function(String, int, String, String?)? f,
  ) {}

  @override
  set badCertificateCallback(
    bool Function(X509Certificate, String, int)? callback,
  ) {}

  @override
  set connectionFactory(
    Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f,
  ) {}

  @override
  set findProxy(String Function(Uri)? f) {}

  @override
  set keyLog(Function(String)? callback) {}

  @override
  void close({bool force = false}) {}

  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) => _fakeRequest();

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> get(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> getUrl(Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> post(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> postUrl(Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> put(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> putUrl(Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> delete(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> head(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> headUrl(Uri url) => _fakeRequest();

  @override
  Future<HttpClientRequest> patch(String host, int port, String path) =>
      _fakeRequest();

  @override
  Future<HttpClientRequest> patchUrl(Uri url) => _fakeRequest();

  Future<HttpClientRequest> _fakeRequest() =>
      Future.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() => Future.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  static const _kTransparentPng = <int>[
    0x89,
    0x50,
    0x4E,
    0x47,
    0x0D,
    0x0A,
    0x1A,
    0x0A,
    0x00,
    0x00,
    0x00,
    0x0D,
    0x49,
    0x48,
    0x44,
    0x52,
    0x00,
    0x00,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    0x01,
    0x08,
    0x06,
    0x00,
    0x00,
    0x00,
    0x1F,
    0x15,
    0xC4,
    0x89,
    0x00,
    0x00,
    0x00,
    0x0A,
    0x49,
    0x44,
    0x41,
    0x54,
    0x78,
    0x9C,
    0x62,
    0x00,
    0x00,
    0x00,
    0x02,
    0x00,
    0x01,
    0xE5,
    0x27,
    0xDE,
    0xFC,
    0x00,
    0x00,
    0x00,
    0x00,
    0x49,
    0x45,
    0x4E,
    0x44,
    0xAE,
    0x42,
    0x60,
    0x82,
  ];

  @override
  int get statusCode => 200;

  @override
  int get contentLength => _kTransparentPng.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([_kTransparentPng]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

class _AuthenticatedAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-access-token',
    refreshToken: 'test-refresh-token',
    ownerId: 'viewer_001',
    activePersonaId: 'viewer_001',
    accountState: 'active',
    identityOrigin: 'widget-test',
    installId: 'widget-test-install',
  );
}

class _GuestAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.guest,
    identityOrigin: 'widget-test-guest',
    installId: 'widget-test-install',
  );
}

class _TestUserProfileRepository extends MockUserProfileRepository
    implements PersonaRelationshipQuery {
  _TestUserProfileRepository({
    required this.bundle,
    this.followers = const <ProfileSocialRelationRowViewData>[],
    this.following = const <ProfileSocialRelationRowViewData>[],
    this.circles = const <PersonaCircleSlice>[],
    this.followersError,
  });

  final UserHomepageBundleViewData bundle;
  final List<ProfileSocialRelationRowViewData> followers;
  final List<ProfileSocialRelationRowViewData> following;
  final List<PersonaCircleSlice> circles;
  final Object? followersError;

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    return bundle;
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    if (followersError != null) {
      throw followersError!;
    }
    return _paginate(_filterRows(followers, query), cursor, limit);
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    return _paginate(_filterRows(following, query), cursor, limit);
  }

  List<ProfileSocialRelationRowViewData> _filterRows(
    List<ProfileSocialRelationRowViewData> rows,
    String? query,
  ) {
    final normalized = query?.trim().toLowerCase() ?? '';
    if (normalized.isEmpty) {
      return rows;
    }
    return rows
        .where((row) {
          return row.displayName.toLowerCase().contains(normalized) ||
              row.userHandle.toLowerCase().contains(normalized);
        })
        .toList(growable: false);
  }

  CursorPage<T> _paginate<T>(List<T> items, String? cursor, int limit) {
    var start = int.tryParse(cursor ?? '') ?? 0;
    if (start < 0) {
      start = 0;
    }
    if (start > items.length) {
      start = items.length;
    }
    final end = start + limit < items.length ? start + limit : items.length;
    return CursorPage<T>(
      items: items.sublist(start, end),
      nextCursor: end < items.length ? '$end' : null,
      totalCount: items.length,
    );
  }
}

final class _TestCircleMembershipQuery implements CircleMembershipQuery {
  _TestCircleMembershipQuery(this.circles);

  final List<PersonaCircleSlice> circles;
  PersonaCircleListQuery? lastPersonaCircleQuery;

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => throw StateError('self membership is not used by ProfileStatsPage');

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => const CircleMembershipPageSlice(items: <CircleMembershipSlice>[]);

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async {
    lastPersonaCircleQuery = query;
    final normalizedQuery = query.query?.trim().toLowerCase() ?? '';
    final filtered = circles
        .where(
          (circle) =>
              normalizedQuery.isEmpty ||
              circle.name.toLowerCase().contains(normalizedQuery) ||
              (circle.description ?? '').toLowerCase().contains(
                normalizedQuery,
              ),
        )
        .toList(growable: false);
    var start = int.tryParse(query.cursor ?? '') ?? 0;
    if (start < 0) {
      start = 0;
    } else if (start > filtered.length) {
      start = filtered.length;
    }
    final candidateEnd = start + query.limit;
    final end = candidateEnd < filtered.length ? candidateEnd : filtered.length;
    return PersonaCirclePageSlice(
      items: filtered.sublist(start, end),
      cursor: end < filtered.length ? '$end' : null,
    );
  }
}

UserHomepageBundleViewData _bundle({
  required String subjectUserId,
  required int followerCount,
  required int followingCount,
  required int circleCount,
  bool isOwner = false,
  bool isGuest = false,
  bool canViewFullProfile = true,
  String relationToTarget = 'not_following',
  String displayName = '测试主页',
  RelationshipCapabilityViewData? relationshipCapability,
}) {
  final profile = PersonaProfileViewData(
    personaId: subjectUserId,
    ownerUserId: isOwner ? subjectUserId : 'owner_$subjectUserId',
    subjectType: 'user',
    userHandle: '${subjectUserId}_handle',
    displayName: displayName,
    avatarUrl: 'https://example.com/$subjectUserId-avatar.png',
    backgroundUrl: 'https://example.com/$subjectUserId-bg.png',
    bio: 'bio',
    followerCount: followerCount,
    followingCount: followingCount,
    postCount: 12,
    circleCount: circleCount,
    likeCount: 33,
    isolationLevel: 'public',
    profileVisibility: 'public',
    inheritsFromOwner: false,
    overriddenFields: const <String>[],
    updatedAt: DateTime(2026, 6, 25),
  );
  final stats = UserProfileStatsViewData.fromProfile(profile);
  return UserHomepageBundleViewData(
    profile: profile,
    stats: stats,
    relationshipCapability: relationshipCapability,
    tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
    viewerContext: UserHomepageViewerContextViewData(
      viewerPersonaId: isGuest ? '' : 'viewer_001',
      isOwner: isOwner,
      isGuest: isGuest,
      relationToTarget: relationToTarget,
      canViewFullProfile: canViewFullProfile,
    ),
    cacheVersion: 'bundle-$subjectUserId',
  );
}

RelationshipCapabilityViewData _capability({
  required String targetId,
  required String relationState,
  bool isBlocked = false,
  bool isBlockedBy = false,
  bool hasFormalConversation = false,
}) {
  final blocked = isBlocked || isBlockedBy;
  final isSelf = relationState == 'self';
  final isMutual = relationState == 'mutual';
  final isFollowing = relationState == 'following' || isMutual;
  final isFollowedBy = relationState == 'followed_by' || isMutual;
  return RelationshipCapabilityViewData(
    viewerPersonaId: isSelf ? targetId : 'viewer_001',
    targetPersonaId: targetId,
    relationState: relationState,
    canFollow: !blocked && !isSelf && !isFollowing,
    canUnfollow: !blocked && isFollowing,
    canFollowBack: !blocked && isFollowedBy && !isFollowing,
    canGreet: !blocked && !isSelf && !isMutual && !hasFormalConversation,
    canOpenConversation: !blocked && (isMutual || hasFormalConversation),
    canCreateDirectConversation: !blocked && isMutual,
    canSendMessage: !blocked && (isMutual || hasFormalConversation),
    hasPendingGreeting: false,
    hasFormalConversation: hasFormalConversation,
    canStartVoiceCall: !blocked && isMutual,
    canStartVideoCall: !blocked && isMutual,
    isBlocked: isBlocked,
    isBlockedBy: isBlockedBy,
  );
}

ProfileSocialRelationRowViewData _row({
  required String id,
  required String displayName,
  required String userHandle,
  String relationState = 'not_following',
  String profileVisibility = 'public',
}) {
  return ProfileSocialRelationRowViewData(
    personaId: id,
    userHandle: userHandle,
    displayName: displayName,
    avatarUrl: 'https://example.com/$id.png',
    profileVisibility: profileVisibility,
    relationState: relationState,
    relationshipCapability: _capability(
      targetId: id,
      relationState: relationState,
    ),
  );
}

PersonaCircleSlice _circle({
  required String id,
  required String name,
  int memberCount = 0,
  int postCount = 0,
  CircleVisibility visibility = CircleVisibility.public,
}) {
  final timestamp = DateTime(2026, 6, 25);
  return PersonaCircleSlice(
    circleId: id,
    name: name,
    coverUrl: 'https://example.com/$id-cover.png',
    ownerPersonaId: 'owner_$id',
    memberCount: memberCount,
    postCount: postCount,
    weeklyActiveCount: 0,
    status: CircleStatus.active,
    visibility: visibility,
    joinPolicy: CircleJoinPolicy.open,
    kind: CircleKind.interest,
    displaySubjectType: CircleDisplaySubjectType.circle,
    followEnabled: true,
    createdAt: timestamp,
    updatedAt: timestamp,
  );
}

Widget _buildTestApp({
  required String type,
  required _TestUserProfileRepository repository,
  String userId = 'profile_target',
  bool authenticated = true,
  _TestCircleMembershipQuery? circleMembershipQuery,
}) {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith((ref, surface) => repository),
      personaRelationshipQueryProvider.overrideWith(
        (ref, surface) => repository,
      ),
      userProfileCircleMembershipQueryProvider.overrideWithValue(
        circleMembershipQuery ?? _TestCircleMembershipQuery(repository.circles),
      ),
      authSessionControllerProvider.overrideWith(
        authenticated
            ? _AuthenticatedAuthSessionController.new
            : _GuestAuthSessionController.new,
      ),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: AppRoutePaths.profileStats(type: type, userId: userId),
        routes: <RouteBase>[
          GoRoute(
            path: AppRoutePaths.profileStatsPathTemplate,
            builder: (_, state) {
              return ProfileStatsPage(
                type: state.uri.queryParameters['type'] ?? 'fans',
                userId: state.uri.queryParameters['userId'] ?? '',
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.loginPathTemplate,
            builder: (_, state) =>
                Text('Login ${state.uri.queryParameters['reason'] ?? ''}'),
          ),
          GoRoute(
            path: AppRoutePaths.circles,
            builder: (_, _) => const Text('Circles Hub'),
          ),
          GoRoute(
            path: AppRoutePaths.circleDetailPathTemplate.replaceAll(
              '{id}',
              ':id',
            ),
            builder: (_, state) => Text('Circle ${state.pathParameters['id']}'),
          ),
          GoRoute(
            path: AppRoutePaths.userProfilePathTemplate.replaceAll(
              '{userHandle}',
              ':username',
            ),
            builder: (_, state) =>
                Text('User ${state.pathParameters['userHandle']}'),
          ),
        ],
      ),
    ),
  );
}

Finder _segmentedControl() =>
    find.byKey(const ValueKey<String>('profile-stats-primary-tabs'));

Finder _segmentedLabel(String label) {
  return find.descendant(of: _segmentedControl(), matching: find.text(label));
}

TextEditingController _searchController(WidgetTester tester) {
  final field = tester.widget<CupertinoSearchTextField>(
    find.byType(CupertinoSearchTextField),
  );
  return field.controller!;
}

Future<void> _pumpFrames(
  WidgetTester tester, {
  int count = 8,
  Duration step = const Duration(milliseconds: 50),
}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(step);
  }
}

Future<void> _pumpInitialLoad(WidgetTester tester) async {
  await tester.pump();
  await _pumpFrames(tester, count: 10);
}

Future<void> _tapSegment(WidgetTester tester, String label) async {
  await tester.tap(_segmentedLabel(label));
  await _pumpFrames(tester);
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
    AuthGate.resetDebounce();
  });

  tearDown(() {
    HttpOverrides.global = null;
    AuthGate.resetDebounce();
  });

  group('ProfileStatsPage 商用重设计', () {
    testWidgets('顶栏使用主页同源一级 Tab，固定三 tab，不包含获赞', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 1,
          followingCount: 1,
          circleCount: 1,
          isOwner: true,
        ),
        followers: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'fan_001',
            displayName: '你的皮炎有点辣',
            userHandle: 'yanla',
            relationState: 'followed_by',
          ),
        ],
        following: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'follow_001',
            displayName: '阿青在路上',
            userHandle: 'aqing',
            relationState: 'following',
          ),
        ],
        circles: <PersonaCircleSlice>[
          _circle(
            id: 'circle_001',
            name: '极简摄影俱乐部',
            memberCount: 2340,
            postCount: 128,
          ),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      expect(_segmentedControl(), findsOneWidget);
      expect(find.byType(CenteredScrollableTabBar), findsOneWidget);
      expect(_segmentedLabel(CommunityText.circleFans), findsOneWidget);
      expect(_segmentedLabel(FoundationText.follow), findsOneWidget);
      expect(_segmentedLabel(ChatText.contactsTabCircles), findsOneWidget);
      expect(find.text('获赞'), findsNothing);
    });

    testWidgets('顶栏一级 Tab 横向拖动不切换 tab，点击才切换', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 1,
          followingCount: 1,
          circleCount: 1,
          isOwner: true,
        ),
        followers: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'fan_001',
            displayName: '你的皮炎有点辣',
            userHandle: 'yanla',
            relationState: 'followed_by',
          ),
        ],
        following: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'follow_001',
            displayName: '阿青在路上',
            userHandle: 'aqing',
            relationState: 'following',
          ),
        ],
        circles: <PersonaCircleSlice>[
          _circle(
            id: 'circle_001',
            name: '极简摄影俱乐部',
            memberCount: 2340,
            postCount: 128,
          ),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      await tester.drag(_segmentedControl(), const Offset(-160, 0));
      await _pumpFrames(tester);

      expect(find.text('你的皮炎有点辣'), findsOneWidget);
      expect(find.text('阿青在路上'), findsNothing);
      await _tapSegment(tester, FoundationText.follow);
      expect(find.text('阿青在路上'), findsOneWidget);
    });

    testWidgets('三 tab 搜索词独立记忆，切换后可恢复', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 2,
          followingCount: 2,
          circleCount: 1,
          isOwner: true,
        ),
        followers: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'fan_001',
            displayName: '你的皮炎有点辣',
            userHandle: 'yanla',
            relationState: 'followed_by',
          ),
          _row(
            id: 'fan_002',
            displayName: '摄影阿青',
            userHandle: 'aqing',
            relationState: 'not_following',
          ),
        ],
        following: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'follow_001',
            displayName: '阿青在路上',
            userHandle: 'aqing',
            relationState: 'following',
          ),
          _row(
            id: 'follow_002',
            displayName: '旅行收藏家',
            userHandle: 'travel_notes',
            relationState: 'mutual',
          ),
        ],
        circles: <PersonaCircleSlice>[
          _circle(id: 'circle_001', name: '极简摄影俱乐部'),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      await tester.enterText(find.byType(CupertinoSearchTextField), '皮炎');
      await _pumpFrames(tester, count: 8);
      expect(_searchController(tester).text, '皮炎');
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
      expect(find.text('摄影阿青'), findsNothing);

      await _tapSegment(tester, FoundationText.follow);
      expect(_searchController(tester).text, isEmpty);

      await tester.enterText(find.byType(CupertinoSearchTextField), '阿青');
      await _pumpFrames(tester, count: 8);
      expect(_searchController(tester).text, '阿青');
      expect(find.text('阿青在路上'), findsOneWidget);
      expect(find.text('旅行收藏家'), findsNothing);

      await _tapSegment(tester, CommunityText.circleFans);
      expect(_searchController(tester).text, '皮炎');
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
      expect(find.text('摄影阿青'), findsNothing);
    });

    testWidgets('他人关注页点击已关注会打开 action sheet', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'author_001',
          followerCount: 1,
          followingCount: 1,
          circleCount: 0,
          relationToTarget: 'following',
          relationshipCapability: _capability(
            targetId: 'author_001',
            relationState: 'following',
          ),
        ),
        following: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'follow_001',
            displayName: '阿青在路上',
            userHandle: 'aqing',
            relationState: 'following',
          ),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(
          type: 'following',
          repository: repository,
          userId: 'author_001',
        ),
      );
      await _pumpInitialLoad(tester);

      await tester.tap(find.text(FoundationText.following));
      await _pumpFrames(tester, count: 6);

      expect(find.text(ProfileText.profileStatsUnfollow), findsOneWidget);
      expect(find.text(ProfileText.profileDirectMessage), findsOneWidget);
    });

    testWidgets('圈子页展示公开圈子并支持跳转详情', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'author_002',
          followerCount: 0,
          followingCount: 0,
          circleCount: 2,
          relationToTarget: 'not_following',
        ),
        circles: <PersonaCircleSlice>[
          _circle(
            id: 'c_public',
            name: '极简摄影俱乐部',
            memberCount: 2340,
            postCount: 128,
          ),
          _circle(id: 'c_travel', name: '旅行手账', memberCount: 86, postCount: 19),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(
          type: 'circles',
          repository: repository,
          userId: 'author_002',
        ),
      );
      await _pumpInitialLoad(tester);

      expect(find.text('极简摄影俱乐部'), findsOneWidget);
      expect(find.text('旅行手账'), findsOneWidget);

      await tester.tap(find.text('极简摄影俱乐部'));
      await _pumpFrames(tester, count: 8);

      expect(find.text('Circle c_public'), findsOneWidget);
    });

    testWidgets('圈子搜索交给云侧 query 分页而不是仅过滤当前页', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'author_002',
          followerCount: 0,
          followingCount: 0,
          circleCount: 2,
        ),
        circles: <PersonaCircleSlice>[
          _circle(id: 'c_photo', name: '极简摄影俱乐部'),
          _circle(id: 'c_travel', name: '旅行手账'),
        ],
      );
      final circleQuery = _TestCircleMembershipQuery(repository.circles);

      await tester.pumpWidget(
        _buildTestApp(
          type: 'circles',
          repository: repository,
          userId: 'author_002',
          circleMembershipQuery: circleQuery,
        ),
      );
      await _pumpInitialLoad(tester);

      await tester.enterText(find.byType(CupertinoSearchTextField), '摄影');
      await _pumpFrames(tester, count: 8);

      expect(circleQuery.lastPersonaCircleQuery?.personaId, 'author_002');
      expect(circleQuery.lastPersonaCircleQuery?.query, '摄影');
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
      expect(find.text('旅行手账'), findsNothing);
    });

    testWidgets('我的圈子空态展示发现入口', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 0,
          followingCount: 0,
          circleCount: 0,
          isOwner: true,
        ),
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'circles', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      expect(
        find.text(ProfileText.profileStatsEmptyCirclesMineTitle),
        findsOneWidget,
      );
      expect(
        find.text(ProfileText.profileStatsDiscoverCircles),
        findsOneWidget,
      );
    });

    testWidgets('隐私主页直接展示权限卡，不渲染伪列表', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'private_user',
          followerCount: 3,
          followingCount: 2,
          circleCount: 1,
          canViewFullProfile: false,
        ),
      );

      await tester.pumpWidget(
        _buildTestApp(
          type: 'fans',
          repository: repository,
          userId: 'private_user',
        ),
      );
      await _pumpInitialLoad(tester);

      expect(find.text(ProfileText.profileStatsPrivateTitle), findsOneWidget);
      expect(find.text(ProfileText.profileStatsPrivateBody), findsOneWidget);
      expect(find.text('你的皮炎有点辣'), findsNothing);
    });

    testWidgets('blocked 主页展示 blocked 卡', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'blocked_user',
          followerCount: 0,
          followingCount: 0,
          circleCount: 0,
          canViewFullProfile: false,
          relationToTarget: 'blocked',
          relationshipCapability: _capability(
            targetId: 'blocked_user',
            relationState: 'not_following',
            isBlockedBy: true,
          ),
        ),
      );

      await tester.pumpWidget(
        _buildTestApp(
          type: 'fans',
          repository: repository,
          userId: 'blocked_user',
        ),
      );
      await _pumpInitialLoad(tester);

      expect(find.text(ProfileText.profileStatsBlockedTitle), findsOneWidget);
      expect(find.text(ProfileText.profileStatsBlockedBody), findsOneWidget);
    });

    testWidgets('self 行不显示关系按钮', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 1,
          followingCount: 0,
          circleCount: 0,
          isOwner: true,
        ),
        followers: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'me',
            displayName: '我自己',
            userHandle: 'me',
            relationState: 'self',
          ),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      expect(find.text('我自己'), findsOneWidget);
      expect(find.text(FoundationText.followBack), findsNothing);
      expect(find.text(FoundationText.following), findsNothing);
      expect(find.text(ProfileText.profileStatsMutual), findsNothing);
    });

    testWidgets('分页滚动到底部后继续加载下一页', (tester) async {
      final followers = List<ProfileSocialRelationRowViewData>.generate(24, (
        index,
      ) {
        final n = index + 1;
        return _row(
          id: 'fan_$n',
          displayName: '粉丝 ${n.toString().padLeft(2, '0')}',
          userHandle: 'fan_$n',
          relationState: 'not_following',
        );
      });
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: followers.length,
          followingCount: 0,
          circleCount: 0,
          isOwner: true,
        ),
        followers: followers,
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      expect(find.text('粉丝 01'), findsOneWidget);
      expect(find.text('粉丝 21'), findsNothing);

      await tester.scrollUntilVisible(
        find.text('粉丝 21'),
        320,
        scrollable: find.byType(Scrollable).first,
      );
      await _pumpFrames(tester, count: 8);

      expect(find.text('粉丝 21'), findsOneWidget);
      expect(find.text('粉丝 24'), findsOneWidget);
    });

    testWidgets('首屏列表拉取失败时展示错误态与重试入口', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'me',
          followerCount: 3,
          followingCount: 0,
          circleCount: 0,
          isOwner: true,
        ),
        followersError: Exception('followers failed'),
      );

      await tester.pumpWidget(
        _buildTestApp(type: 'fans', repository: repository, userId: 'me'),
      );
      await _pumpInitialLoad(tester);

      expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
      expect(find.text(SearchText.reload), findsOneWidget);
    });

    testWidgets('游客点击关注会进入登录页', (tester) async {
      final repository = _TestUserProfileRepository(
        bundle: _bundle(
          subjectUserId: 'author_guest',
          followerCount: 1,
          followingCount: 0,
          circleCount: 0,
          isGuest: true,
        ),
        followers: <ProfileSocialRelationRowViewData>[
          _row(
            id: 'fan_001',
            displayName: '你的皮炎有点辣',
            userHandle: 'yanla',
            relationState: 'not_following',
          ),
        ],
      );

      await tester.pumpWidget(
        _buildTestApp(
          type: 'fans',
          repository: repository,
          userId: 'author_guest',
          authenticated: false,
        ),
      );
      await _pumpInitialLoad(tester);

      await tester.tap(
        find.descendant(
          of: find.byType(CustomScrollView),
          matching: find.text(FoundationText.follow),
        ),
      );
      await _pumpFrames(tester, count: 10);

      expect(find.text('Login follow'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
    });
  });
}
