import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/interest_onboarding.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/interest_onboarding_writer.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/interest_onboarding_dependencies.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/interest_onboarding_page.dart';

void main() {
  testWidgets('加载 typed 标签并在确认提交后回到首页', (tester) async {
    final store = _MemoryDraftStore();
    final writer = _RecordingWriter();
    final query = _TagCatalogQuery();
    final router = _router();
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          tagCatalogQueryProvider.overrideWithValue(query),
          interestOnboardingCoordinatorProvider.overrideWithValue(
            InterestOnboardingCoordinator(draftStore: store, writer: writer),
          ),
        ],
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('旅行'), findsOneWidget);
    final option = find.byKey(
      const ValueKey<String>('interest-onboarding-option-Topic/兴趣/旅行'),
    );
    final unselectedColor = tester.widget<CupertinoButton>(option).color;
    await tester.tap(option);
    await tester.pump();
    expect(
      tester.widget<CupertinoButton>(option).color,
      isNot(unselectedColor),
    );
    await tester.tap(find.text(ProfileText.interestOnboardingSubmit));
    await tester.pumpAndSettle();

    expect(
      writer.submittedTagRefs,
      <String>['Topic/兴趣/旅行'],
      reason: tester
          .widgetList<Text>(find.byType(Text))
          .map((widget) => widget.data)
          .whereType<String>()
          .join(' | '),
    );
    expect(query.parentRequests, contains('Topic/兴趣'));
    expect(store.draft?.status, InterestOnboardingStatus.submitted);
    expect(find.text('home'), findsOneWidget);
  });

  testWidgets('提交回显云侧目录下发的 taxonomyReleaseId，而非编译常量', (tester) async {
    final writer = _RecordingWriter();
    final query = _TagCatalogQuery(releaseId: 'tag-taxonomy-live-20990101-007');
    final router = _router();
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          tagCatalogQueryProvider.overrideWithValue(query),
          interestOnboardingCoordinatorProvider.overrideWithValue(
            InterestOnboardingCoordinator(
              draftStore: _MemoryDraftStore(),
              writer: writer,
            ),
          ),
        ],
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('旅行'));
    await tester.tap(find.text(ProfileText.interestOnboardingSubmit));
    await tester.pumpAndSettle();

    expect(writer.taxonomyReleaseIds, <String>[
      'tag-taxonomy-live-20990101-007',
    ]);
  });

  testWidgets('标签读取失败时呈现重试，重试后恢复真实目录项', (tester) async {
    final query = _TagCatalogQuery(shouldFail: true);
    final router = _router();
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          tagCatalogQueryProvider.overrideWithValue(query),
          interestOnboardingCoordinatorProvider.overrideWithValue(
            InterestOnboardingCoordinator(
              draftStore: _MemoryDraftStore(),
              writer: _RecordingWriter(),
            ),
          ),
        ],
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final errorState = tester.widget<AppPageErrorState>(
      find.byType(AppPageErrorState),
    );
    expect(errorState.semantic.message.trim(), isNotEmpty);
    expect(errorState.semantic.primaryAction?.label, SearchText.reload);
    query.shouldFail = false;
    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    expect(find.text('旅行'), findsOneWidget);
  });

  testWidgets('游客关闭登录后回安全首页且不会再次触发登录门', (tester) async {
    final writer = _RecordingWriter();
    final router = _router();
    final container = ProviderContainer(
      overrides: [
        authSessionControllerProvider.overrideWith(_GuestSession.new),
        tagCatalogQueryProvider.overrideWithValue(_TagCatalogQuery()),
        interestOnboardingCoordinatorProvider.overrideWithValue(
          InterestOnboardingCoordinator(
            draftStore: _MemoryDraftStore(),
            writer: writer,
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('旅行'));
    await tester.tap(find.text(ProfileText.interestOnboardingSubmit));
    await tester.pumpAndSettle();

    expect(find.text('dismiss login'), findsOneWidget);
    await tester.tap(find.text('dismiss login'));
    await tester.pumpAndSettle();
    await tester.pump();

    expect(find.text('home'), findsOneWidget);
    expect(find.text('dismiss login'), findsNothing);
    expect(container.read(authContinuationProvider), isNull);
    expect(writer.submittedTagRefs, isEmpty);
  });

  testWidgets('登录成功后用原 client event id 续接兴趣提交', (tester) async {
    final writer = _RecordingWriter();
    final router = _router();
    final container = ProviderContainer(
      overrides: [
        authSessionControllerProvider.overrideWith(_GuestSession.new),
        tagCatalogQueryProvider.overrideWithValue(_TagCatalogQuery()),
        interestOnboardingCoordinatorProvider.overrideWithValue(
          InterestOnboardingCoordinator(
            draftStore: _MemoryDraftStore(),
            writer: writer,
          ),
        ),
      ],
    );
    final session =
        container.read(authSessionControllerProvider.notifier) as _GuestSession;
    addTearDown(router.dispose);
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('旅行'));
    await tester.tap(find.text(ProfileText.interestOnboardingSubmit));
    await tester.pumpAndSettle();

    final continuation =
        container.read(authContinuationProvider)
            as SubmitOnboardingInterestContinuation;
    session.authenticate();
    await tester.pumpAndSettle();

    expect(writer.clientEventIds, <String>[continuation.clientEventId]);
    expect(writer.submittedTagRefs, continuation.tagRefs);
    expect(find.text('home'), findsOneWidget);
    expect(container.read(authContinuationProvider), isNull);
  });
}

GoRouter _router() => GoRouter(
  initialLocation: AppRoutePaths.interestOnboarding,
  routes: <RouteBase>[
    GoRoute(
      path: AppRoutePaths.interestOnboarding,
      builder: (_, _) => InterestOnboardingPage(),
    ),
    GoRoute(path: AppRoutePaths.home, builder: (_, _) => const Text('home')),
    GoRoute(
      path: AppRoutePaths.loginPathTemplate,
      builder: (context, state) => Consumer(
        builder: (context, ref, _) => CupertinoPageScaffold(
          child: Center(
            child: CupertinoButton(
              onPressed: () {
                // Mirror LoginPage._dismissAsGuest: clear pending continuation.
                ref.read(authContinuationProvider.notifier).clear();
                context.go(
                  state.uri.queryParameters[loginDismissFallbackQueryParam] ??
                      AppRoutePaths.home,
                );
              },
              child: const Text('dismiss login'),
            ),
          ),
        ),
      ),
    ),
  ],
);

final class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'token',
    refreshToken: 'refresh-token',
    ownerId: 'owner_1',
    activePersonaId: 'persona_1',
  );
}

final class _GuestSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void authenticate() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'token',
      refreshToken: 'refresh-token',
      ownerId: 'owner_1',
      activePersonaId: 'persona_1',
    );
  }
}

final class _MemoryDraftStore implements InterestOnboardingDraftStore {
  InterestOnboardingDraft? draft;

  @override
  Future<InterestOnboardingDraft?> read() async => draft;

  @override
  Future<void> write(InterestOnboardingDraft next) async {
    draft = next;
  }
}

final class _RecordingWriter implements ConfirmedOnboardingInterestWriter {
  List<String> submittedTagRefs = const <String>[];
  final List<String> clientEventIds = <String>[];
  final List<String> taxonomyReleaseIds = <String>[];

  @override
  Future<void> submit({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    clientEventIds.add(clientEventId);
    taxonomyReleaseIds.add(taxonomyReleaseId);
    submittedTagRefs = List<String>.unmodifiable(tagRefs);
  }
}

final class _TagCatalogQuery implements TagCatalogQuery {
  _TagCatalogQuery({this.shouldFail = false, this.releaseId = _defaultRelease});

  /// 刻意与任何编译期常量不同：提交必须回显本次目录的发布号，
  /// 这样发一个新 tag 发布不需要重发端。
  static const String _defaultRelease = 'tag-taxonomy-published-after-build';

  bool shouldFail;
  final String releaseId;
  final List<String> parentRequests = <String>[];

  @override
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    parentRequests.add(parentTagRef);
    if (shouldFail) {
      throw StateError('catalog unavailable');
    }
    switch (parentTagRef) {
      case 'Topic':
        return <TagChildView>[
          _child(
            tagRef: 'Topic/兴趣',
            label: '兴趣',
            parentTagRef: parentTagRef,
            hasChildren: true,
          ),
        ];
      case 'Topic/兴趣':
        return <TagChildView>[
          _child(
            tagRef: 'Topic/兴趣/旅行',
            label: '旅行',
            parentTagRef: parentTagRef,
          ),
        ];
      case 'Audience':
        return <TagChildView>[
          _child(
            tagRef: 'Audience/用户/摄影爱好者',
            label: '摄影爱好者',
            parentTagRef: parentTagRef,
          ),
        ];
      case 'Format':
        return <TagChildView>[
          _child(
            tagRef: 'Format/内容/图文',
            label: '图文',
            parentTagRef: parentTagRef,
          ),
        ];
      case 'Entity':
        return <TagChildView>[
          _child(
            tagRef: 'Entity/地点/旅行目的地',
            label: '旅行目的地',
            parentTagRef: parentTagRef,
          ),
        ];
      default:
        return const <TagChildView>[];
    }
  }

  TagChildView _child({
    required String tagRef,
    required String label,
    required String parentTagRef,
    bool hasChildren = false,
  }) {
    return TagChildView(
      tagRef: tagRef,
      label: label,
      displayLabel: label,
      labelEn: '',
      parentTagRef: parentTagRef,
      depth: tagRef.split('/').length - 1,
      hasChildren: hasChildren,
      releaseId: releaseId,
      lifecycleStatus: TagLifecycleStatus.active,
    );
  }

  @override
  Future<TagResolveView> resolveTag(String tagRef) => _unsupported();

  @override
  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) => _unsupported();

  Future<T> _unsupported<T>() =>
      Future<T>.error(UnsupportedError('unused in this page contract'));
}
