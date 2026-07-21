import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/recording_content_media_facet.dart';
import '../../../../support/recording_content_post_publication_writer.dart';
import '../../../../support/recording_circle_post_placement_writer.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

const _resolvedActivePersona = ActivePersonaContextViewData(
  subAccountId: 'user_001',
  ownerUserId: 'user_001',
  subjectType: 'subAccount',
  displayName: '测试用户',
  avatarUrl: '',
  personaContextVersion: '1',
  isPrimary: true,
);

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
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'user_001',
      activeSubAccountId: 'user_001',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
    );
  }
}

/// 在 pump 期间主动 watch 登录态，让创作页发布/选图的 requireLogin 在已登录态放行。
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
  const _CreateHostApp({this.initialCircleId});

  final String? initialCircleId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.of(context).push<void>(
              MaterialPageRoute<void>(
                builder: (_) => CreatePage(
                  initialCircleId: initialCircleId,
                  initialCircleName: initialCircleId == null ? null : '测试圈子',
                ),
              ),
            );
          },
          child: const Text('打开创作'),
        ),
      ),
    );
  }
}

List<Override> _createPublishOverrides(
  MockContentRepository repository,
  RecordingContentPostPublicationWriter postPublication,
  RecordingContentMediaFacet media,
) => <Override>[
  ...mockContentFacetOverrides(repository),
  createContentPostPublicationWriterProvider.overrideWithValue(postPublication),
  createContentMediaFacetProvider.overrideWithValue(media),
  contentMediaStreamObjectUploadProvider.overrideWithValue(
    (
      uploadUri,
      bytes, {
      required contentLength,
      required contentType,
      required expectedSha256,
      abortTrigger,
    }) async {},
  ),
];

Widget _buildApp(
  MockContentRepository repository,
  RecordingContentPostPublicationWriter postPublication, {
  RecordingCirclePostPlacementWriter? placements,
  RecordingContentMediaFacet? media,
  String? initialCircleId,
}) {
  final mediaFacet = media ?? RecordingContentMediaFacet();
  return ProviderScope(
    overrides: [
      activePersonaContextProvider.overrideWith(
        (_) async => _resolvedActivePersona,
      ),
      ..._createPublishOverrides(repository, postPublication, mediaFacet),
      if (placements != null)
        createWorkspaceCirclePostPlacementWriterProvider.overrideWithValue(
          placements,
        ),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            _AuthWarmup(child: child ?? const SizedBox.shrink()),
        home: _CreateHostApp(initialCircleId: initialCircleId),
      ),
    ),
  );
}

Widget _buildRouterApp(
  MockContentRepository repository,
  RecordingContentPostPublicationWriter postPublication,
) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => const _CreateHostApp()),
      GoRoute(
        path: AppRoutePaths.homepagePickerPathTemplate,
        builder: (context, state) {
          final extra = state.extra is HomepagePickerPageRouteExtra
              ? state.extra! as HomepagePickerPageRouteExtra
              : null;
          return HomepagePickerPage(
            initialQuery: state.uri.queryParameters['query'] ?? '',
            initialSelection: extra?.initialSelection,
          );
        },
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      activePersonaContextProvider.overrideWith(
        (_) async => _resolvedActivePersona,
      ),
      ..._createPublishOverrides(
        repository,
        postPublication,
        RecordingContentMediaFacet(),
      ),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
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

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('短文本直接按 micro 契约发布，且不暴露旧 taxonomy', (tester) async {
    final repository = MockContentRepository();
    final postPublication = RecordingContentPostPublicationWriter();

    await tester.pumpWidget(_buildApp(repository, postPublication));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '今天很开心');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('允许小趣使用'), findsNothing);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(postPublication.submitCommands, hasLength(1));
    expect(postPublication.lastSubmitPayload?['contentType'], 'micro');
    expect(
      postPublication.lastSubmitPayload?.containsKey('contentIdentity'),
      isFalse,
    );
    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsOneWidget,
    );
    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    expect(find.text('当前内容更适合作为作品发布'), findsNothing);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('打开创作'), findsOneWidget);
  });

  testWidgets('长文本直接进入下一步并按 article 契约发布，且不暴露旧 taxonomy', (tester) async {
    final repository = MockContentRepository();
    final postPublication = RecordingContentPostPublicationWriter();

    await tester.pumpWidget(_buildApp(repository, postPublication));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final longText = '准备升级为作品的长文案' * 16;
    await tester.enterText(find.byKey(TestKeys.createMomentInput), longText);
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    final dialog = find.byType(CupertinoAlertDialog);
    expect(dialog, findsNothing);
    expect(find.text('当前内容更适合作为作品发布'), findsNothing);
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(postPublication.submitCommands, hasLength(1));
    expect(postPublication.lastSubmitPayload?['contentType'], 'article');
    expect(postPublication.lastSubmitPayload?.containsKey('body'), isFalse);
    expect(
      postPublication.lastSubmitPayload?.containsKey('articleTemplate'),
      isFalse,
    );
    expect(
      postPublication.lastSubmitPayload?.containsKey('articleFontPreset'),
      isFalse,
    );
    expect(
      postPublication.lastSubmitPayload?['articleMarkdown'],
      isA<String>(),
    );
    expect(
      postPublication.lastSubmitPayload?['markdownDialect'],
      'qwq-rich-md',
    );
    expect(
      postPublication.lastSubmitPayload?['articleAssetManifest'],
      isA<Map<String, dynamic>>(),
    );
    expect(
      postPublication.lastSubmitPayload?['articleRenderProfile'],
      isA<Map<String, dynamic>>(),
    );
    final articleMarkdown =
        postPublication.lastSubmitPayload?['articleMarkdown'] as String;
    expect(articleMarkdown.contains(longText), isTrue);
    final renderProfile =
        postPublication.lastSubmitPayload?['articleRenderProfile']
            as Map<String, dynamic>;
    expect(renderProfile['template'], isNotNull);
    expect(renderProfile['fontPreset'], isNotNull);
    expect(
      postPublication.lastSubmitPayload?.containsKey('articlePages'),
      isFalse,
    );
    expect(
      postPublication.lastSubmitPayload?.containsKey('articleBlocks'),
      isFalse,
    );
    expect(postPublication.lastSubmitPayload?.containsKey('cards'), isFalse);
    expect(
      postPublication.lastSubmitPayload?.containsKey('articleDocument'),
      isFalse,
    );
    expect(
      postPublication.lastSubmitPayload?.containsKey('contentIdentity'),
      isFalse,
    );
    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('打开创作'), findsOneWidget);
  });

  testWidgets('媒体编辑器对图片使用首图预览并写入 payload', (tester) async {
    final repository = MockContentRepository();
    final postPublication = RecordingContentPostPublicationWriter();
    final media = RecordingContentMediaFacet();
    const coverA = 'asset://image_asset_a';
    const coverB = 'asset://image_asset_b';

    await tester.pumpWidget(
      _buildApp(repository, postPublication, media: media),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      coverA,
      coverB,
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(1);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('当前封面'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    for (var i = 0; i < 10 && postPublication.lastSubmitPayload == null; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }

    final payload = postPublication.lastSubmitPayload;
    expect(payload, isNotNull);
    expect(payload?['contentType'], 'image');
    expect(payload?.containsKey('mediaUrls'), isFalse);
    expect(payload?.containsKey('coverUrl'), isFalse);
    expect(payload?['mediaItems'], <Map<String, Object?>>[
      <String, Object?>{'kind': 'image', 'mediaId': 'image_asset_a'},
      <String, Object?>{'kind': 'image', 'mediaId': 'image_asset_b'},
    ]);
    expect(postPublication.submitCommands.single.mediaAssetIds, <String>[
      'image_asset_a',
      'image_asset_b',
    ]);
    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });

  testWidgets('圈子锚点在 Post 发布后通过 CirclePostPlacement Facade 放置', (tester) async {
    final repository = MockContentRepository();
    final postPublication = RecordingContentPostPublicationWriter();
    final placements = RecordingCirclePostPlacementWriter();

    await tester.pumpWidget(
      _buildApp(
        repository,
        postPublication,
        placements: placements,
        initialCircleId: 'circle-west-sichuan',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(TestKeys.createMomentInput), '圈内发布');
    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(postPublication.submitCommands, hasLength(1));
    expect(postPublication.lastSubmitPayload, isNot(contains('circleIds')));
    expect(placements.commands, hasLength(1));
    expect(placements.commands.single.circleId, 'circle-west-sichuan');
    expect(placements.commands.single.postId, 'post_test_1');
    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });

  testWidgets('发布设置页可进入统一返回页风格的主页与圈子选择', (tester) async {
    final repository = MockContentRepository();
    final postPublication = RecordingContentPostPublicationWriter();

    await tester.pumpWidget(_buildRouterApp(repository, postPublication));
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开创作'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '测试发布设置');
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.createPublishButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
    expect(find.text('发布设置'), findsOneWidget);

    await tester.tap(find.text('关联主页'));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.homepagePickerPage), findsOneWidget);
    expect(find.byKey(TestKeys.homepagePickerConfirmButton), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.homepagePickerCancelButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);

    await tester.tap(find.text('发布到圈子'));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.publishCircleSelectPage), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);

    await tester.tap(find.byKey(TestKeys.publishCircleCancelButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.createPublishConfirmSheet), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
