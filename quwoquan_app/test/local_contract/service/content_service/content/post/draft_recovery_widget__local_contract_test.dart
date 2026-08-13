import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/local_draft_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_draft_local_storage.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/integration_service/external_integration/location/location_typed_double.dart';
import '../../../../../support/service/user_service/account/account_session/account_session_typed_double.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/runtime/transport/recording_content_media_facet.dart';
import '../../../../../support/service/content_service/content/post/recording_content_post_publication_writer.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';

const _resolvedActivePersona = ActivePersonaContextViewData(
  personaId: 'user_001',
  ownerUserId: 'user_001',
  subjectType: 'persona',
  displayName: '测试用户',
  avatarUrl: '',
  contextVersion: 1,
  isPrimary: true,
);

class _AuthedSessionStore implements AuthSessionStore {
  _AuthedSessionStore();

  /// 本用例的前置是「刚刚刷新过的活跃会话」：restore 期不得再触发
  /// `refreshSessionIfNeeded`，否则会话会被判过期、发布入口退回登录门。
  final int _lastRefreshAtEpochMs = DateTime.now().millisecondsSinceEpoch;

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: _lastRefreshAtEpochMs,
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
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> updateActivePersona(String personaId) async {}
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
                MaterialPageRoute<void>(builder: (_) => CreatePage()),
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

Widget _buildApp(
  InMemoryContentPostStore store,
  RecordingContentPostPublicationWriter postPublication,
) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => const _CreateHostApp()),
      GoRoute(
        path: AppRoutePaths.localDrafts,
        builder: (context, state) => LocalDraftPage(),
      ),
      GoRoute(
        path: AppRoutePaths.createPathTemplate,
        builder: (context, state) {
          final type = (state.uri.queryParameters['type'] ?? '').trim();
          return CreatePage(
            initialAction: switch (type) {
              'gallery' => EditorStartAction.gallery,
              'video' => EditorStartAction.video,
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
      ...sealedCloudBoundaryOverrides(),
      currentUserIdProvider.overrideWithValue('user_001'),
      activePersonaContextProvider.overrideWith(
        (_) async => _resolvedActivePersona,
      ),
      ...mockContentFacetOverrides(store: store),
      createContentPostPublicationWriterProvider.overrideWithValue(
        postPublication,
      ),
      createContentMediaFacetProvider.overrideWithValue(
        RecordingContentMediaFacet(),
      ),
      contentMediaStreamObjectUploadProvider.overrideWithValue(
        (
          uploadUri,
          bytes, {
          required contentLength,
          required mimeType,
          required expectedSha256,
          abortTrigger,
        }) async {},
      ),
      circlesListQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
      startupAuthRestoreGateProvider.overrideWith(() => _OpenStartupAuthGate()),
      authSessionStoreProvider.overrideWithValue(_AuthedSessionStore()),
      // 创建页壳还会拉起会话生命周期与「附近地点」读面：给对象级 typed double，
      // 否则 provider 图会一路走到被封死的 generated operation client。
      accountSessionCommandWriterProvider.overrideWithValue(
        InMemoryAccountSessionFacet(),
      ),
      createLocationNearbyReaderProvider.overrideWithValue(
        LocationQueryTypedDouble(),
      ),
      createLocationSearchReaderProvider.overrideWithValue(
        LocationQueryTypedDouble(),
      ),
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
    final store = InMemoryContentPostStore();
    final postPublication = RecordingContentPostPublicationWriter();
    final draftRepository = SharedPreferencesCreateDraftRepository(
      scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user_001'),
    );

    await tester.pumpWidget(_buildApp(store, postPublication));
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

    expect(postPublication.submitCommands, hasLength(1));
    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.localDraftPage), findsOneWidget);
    expect(find.byKey(TestKeys.localDraftEmptyState), findsOneWidget);
    expect((await draftRepository.load()).drafts, isEmpty);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });
}
