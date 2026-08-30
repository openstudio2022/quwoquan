import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import '../../../../../support/runtime/homepage_source_cards_boundary_overrides.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show FoundationText, ObjectHomepageText;
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider, intersectionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailEntityWishlistStateReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentRuntimeConfigProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart'
    show buildProductionContentRuntimeConfigDefaults;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider, contentBehaviorTrackerProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String _homepageId = 'homepage_sight_west_lake';

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
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

  testWidgets('地点主页读取真实想去状态并上报添加与移除事实', (tester) async {
    final reader = _WishlistStateReader(wishlisted: false);
    final reporter = _RecordingBehaviorReporter();
    final tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...homepageSourceCardsBoundaryOverrides(),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            InMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            reader,
          ),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
          currentUserIdProvider.overrideWithValue('homepage-viewer-persona'),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(reader.calls, 1);
    expect(
      find.widgetWithText(
        ProfileIosActionButton,
        ObjectHomepageText.homepageWishlistAction,
      ),
      findsOneWidget,
    );
    expect(
      find.widgetWithText(ProfileIosActionButton, FoundationText.follow),
      findsNothing,
    );

    await tester.tap(
      find.widgetWithText(
        ProfileIosActionButton,
        ObjectHomepageText.homepageWishlistAction,
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.homepageWishlistedAction),
      findsOneWidget,
    );
    expect(reporter.events, hasLength(1));
    expect(reporter.events.single.action, BehaviorEventType.wishlistAdd);
    expect(reporter.events.single.objectId, _homepageId);
    expect(reporter.events.single.objectKind, 'homepage');
    expect(
      reporter.events.single.sourceSurface,
      AppUiSurfaces.homepageDetail.id,
    );

    await tester.tap(
      find.widgetWithText(
        ProfileIosActionButton,
        ObjectHomepageText.homepageWishlistedAction,
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.homepageWishlistAction),
      findsOneWidget,
    );
    expect(reporter.events, hasLength(2));
    expect(reporter.events.last.action, BehaviorEventType.wishlistRemove);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('云侧已想去状态在首帧加载完成后保持选中', (tester) async {
    final tracker = ContentBehaviorTracker(
      reporter: _RecordingBehaviorReporter(),
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...homepageSourceCardsBoundaryOverrides(),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            InMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            _WishlistStateReader(wishlisted: true),
          ),
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.homepageWishlistedAction),
      findsOneWidget,
    );
  });

  testWidgets('非地点主页不读取想去状态并保留关注语义', (tester) async {
    final reader = _WishlistStateReader(wishlisted: true);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...homepageSourceCardsBoundaryOverrides(),
          behaviorRepositoryProvider.overrideWithValue(
            RecordingContentBehaviorRepository(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            InMemoryIntersectionRepository(),
          ),
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'homepage-viewer-persona',
              ownerUserId: 'homepage-viewer-owner',
              displayName: '主页测试用户',
              avatarUrl: '',
            ),
          ),
          homepageFacetSetProvider.overrideWithValue(
            _UniversityHomepageRepository(),
          ),
          homepageIntroductionRepositoryProvider.overrideWithValue(
            const MockHomepageIntroductionRepository(),
          ),
          homepageDetailEntityWishlistStateReaderProvider.overrideWithValue(
            reader,
          ),
        ],
        child: const MaterialApp(
          home: HomepageDetailPage(homepageId: _homepageId),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(reader.calls, 0);
    expect(
      find.widgetWithText(ProfileIosActionButton, FoundationText.follow),
      findsOneWidget,
    );
    expect(
      find.widgetWithText(
        ProfileIosActionButton,
        ObjectHomepageText.homepageWishlistAction,
      ),
      findsNothing,
    );
  });
}

final class _AuthenticatedHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'homepage-access-token',
    refreshToken: 'homepage-refresh-token',
    ownerId: 'homepage-viewer-owner',
    activePersonaId: 'homepage-viewer-persona',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'homepage-install-id',
  );
}

final class _WishlistStateReader implements ContentEntityWishlistStateReader {
  _WishlistStateReader({required this.wishlisted});

  final bool wishlisted;
  int calls = 0;

  @override
  Future<EntityWishlistState> getEntityWishlistState({
    required String objectId,
    required String objectKind,
  }) async {
    calls += 1;
    return EntityWishlistState(
      objectId: objectId,
      objectKind: objectKind,
      wishlisted: wishlisted,
    );
  }
}

final class _RecordingBehaviorReporter implements BehaviorReporter {
  final List<BehaviorEvent> events = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    this.events.addAll(events);
  }
}

final class _UniversityHomepageRepository extends MockHomepageRepository {
  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final detail = await super.getHomepageDetail(_homepageId);
    return detail.copyWith(
      id: homepageId,
      homepageType: 'university',
      title: '示例大学',
    );
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final detail = await getHomepageDetail(homepageId);
    return HomepageShellData(homepage: detail);
  }
}

final class _NoNetworkHttpOverrides extends HttpOverrides {}
