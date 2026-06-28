import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/local_draft_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _TrackingContentRepository extends MockContentRepository {
  int createCallCount = 0;
  int publishCallCount = 0;

  @override
  Future<PostBaseDto> createPost({required CreatePostRequestWire body}) async {
    createCallCount += 1;
    const postId = 'post_from_draft';
    return postBaseDtoFromMap(<String, dynamic>{
      'postId': postId,
      ...body.toWire(),
      'authorId': 'user_001',
      'displayName': 'Tester',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
    });
  }

  @override
  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  }) async {
    publishCallCount += 1;
    final wire = body ?? PublishPostRequestWire();
    return postBaseDtoFromMap(<String, dynamic>{
      'postId': postId,
      ...wire.toWire(),
      'authorId': 'user_001',
      'displayName': 'Tester',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'contentType': 'micro',
      'body': '',
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
    });
  }
}

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activeSubAccountId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}
}

class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}

class _CreateHostApp extends StatelessWidget {
  const _CreateHostApp();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(builder: (_) => const CreatePage()),
              );
            },
            child: const Text('打开创作'),
          ),
          ElevatedButton(
            onPressed: () => context.push(AppRoutePaths.localDrafts),
            child: const Text('打开本地草稿'),
          ),
        ],
      ),
    );
  }
}

Widget _buildApp(_TrackingContentRepository repository) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => const _CreateHostApp()),
      GoRoute(
        path: AppRoutePaths.localDrafts,
        builder: (context, state) => const LocalDraftPage(),
      ),
      GoRoute(
        path: AppRoutePaths.createPathTemplate,
        builder: (context, state) {
          final type = (state.uri.queryParameters['type'] ?? '').trim();
          return CreatePage(
            initialAction: switch (type) {
              'gallery' => EditorStartAction.gallery,
              'capture' => EditorStartAction.capture,
              'write' => EditorStartAction.write,
              _ => null,
            },
            initialDraftId: state.uri.queryParameters['draftId'],
          );
        },
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      contentRepositoryProvider.overrideWithValue(repository),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
      startupAuthRestoreGateProvider.overrideWith(() => _OpenStartupAuthGate()),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp.router(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            _AuthWarmup(child: child ?? const SizedBox.shrink()),
        routerConfig: router,
      ),
    ),
  );
}

class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('退出保存后可从本地草稿页恢复，并在发布成功后清稿', (tester) async {
    final repository = _TrackingContentRepository();
    final draftRepository = SharedPreferencesCreateDraftRepository(
      scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
    );

    await tester.pumpWidget(_buildApp(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '待会继续写的内容');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createCloseButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createSaveAndExitButton));
    await tester.pumpAndSettle();

    expect(find.text('打开创作'), findsOneWidget);
    final savedDrafts = await draftRepository.load();
    expect(savedDrafts.drafts, hasLength(1));
    final draftId = savedDrafts.drafts.single.id;

    await tester.tap(find.text('打开本地草稿'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.localDraftPage), findsOneWidget);
    await tester.tap(find.byKey(ValueKey<String>('local_draft_card_$draftId')));
    await tester.pumpAndSettle();

    expect(find.text('待会继续写的内容'), findsOneWidget);

    await tester.ensureVisible(find.byKey(TestKeys.createPublishButton));
    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    await tester.ensureVisible(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));

    expect(repository.createCallCount, 1);
    expect(repository.publishCallCount, 1);
    expect(find.byKey(TestKeys.localDraftPage), findsOneWidget);
    expect(find.byKey(TestKeys.localDraftEmptyState), findsOneWidget);
    expect((await draftRepository.load()).drafts, isEmpty);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });
}
