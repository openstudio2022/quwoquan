import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';
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
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'homepage-viewer-persona',
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
        UITextConstants.homepageWishlistAction,
      ),
      findsOneWidget,
    );
    expect(
      find.widgetWithText(ProfileIosActionButton, UITextConstants.follow),
      findsNothing,
    );

    await tester.tap(
      find.widgetWithText(
        ProfileIosActionButton,
        UITextConstants.homepageWishlistAction,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.homepageWishlistedAction), findsOneWidget);
    expect(reporter.events, hasLength(1));
    expect(reporter.events.single.action, BehaviorAction.wishlistAdd);
    expect(reporter.events.single.objectId, _homepageId);
    expect(reporter.events.single.objectKind, 'homepage');
    expect(
      reporter.events.single.sourceSurface,
      AppUiSurfaces.homepageDetail.id,
    );

    await tester.tap(
      find.widgetWithText(
        ProfileIosActionButton,
        UITextConstants.homepageWishlistedAction,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.homepageWishlistAction), findsOneWidget);
    expect(reporter.events, hasLength(2));
    expect(reporter.events.last.action, BehaviorAction.wishlistRemove);
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
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'homepage-viewer-persona',
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

    expect(find.text(UITextConstants.homepageWishlistedAction), findsOneWidget);
  });

  testWidgets('非地点主页不读取想去状态并保留关注语义', (tester) async {
    final reader = _WishlistStateReader(wishlisted: true);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHomepageSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'homepage-viewer-persona',
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
      find.widgetWithText(ProfileIosActionButton, UITextConstants.follow),
      findsOneWidget,
    );
    expect(
      find.widgetWithText(
        ProfileIosActionButton,
        UITextConstants.homepageWishlistAction,
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
    ownerId: 'homepage-viewer-owner',
    activeSubAccountId: 'homepage-viewer-persona',
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
