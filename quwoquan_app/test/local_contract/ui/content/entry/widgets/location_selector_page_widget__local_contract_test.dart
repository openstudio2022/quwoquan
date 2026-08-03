import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/l10n/app_localizations_zh.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../support/fake_location_gateway.dart';
import '../../../../../support/fake_location_readers.dart';
import '../../../../../support/runtime_failure_fixtures.dart';

final class _PendingLocationQuery
    implements NearbyLocationReader, LocationSearchReader {
  _PendingLocationQuery(this.completer);

  final Completer<LocationPoiListSlice> completer;

  @override
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  ) {
    return completer.future;
  }

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    return const LocationPoiListSlice(items: []);
  }
}

CreateLocationCoordinator _coordinator({
  required LocationGateway gateway,
  required NearbyLocationReader nearbyReader,
  LocationSearchReader? searchReader,
}) {
  final effectiveSearchReader = searchReader ?? _searchReaderFrom(nearbyReader);
  return CreateLocationCoordinator(
    nearbyReader: nearbyReader,
    searchReader: effectiveSearchReader,
    locationGateway: gateway,
  );
}

LocationSearchReader _searchReaderFrom(NearbyLocationReader reader) {
  if (reader is LocationSearchReader) {
    return reader as LocationSearchReader;
  }
  return FakeLocationQueryAdapter();
}

/// L1b Widget 测试：位置选择页权限永久拒绝 → 展示 locationAppPermissionRequired + 去设置
///
/// 规范：specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md
/// 特性树：permission-card-display-contract
void main() {
  for (final profile in <({String name, Size size, Brightness brightness})>[
    (
      name: 'compact/light',
      size: const Size(375, 812),
      brightness: Brightness.light,
    ),
    (
      name: 'regular/dark',
      size: const Size(768, 1024),
      brightness: Brightness.dark,
    ),
    (
      name: 'expanded/light',
      size: const Size(1280, 900),
      brightness: Brightness.light,
    ),
  ]) {
    testWidgets('${profile.name} 使用同一 Location Slice', (tester) async {
      tester.view.physicalSize = profile.size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final query = FakeLocationQueryAdapter(
        items: <LocationPoi>[
          LocationPoi(
            id: 'fixture_poi',
            name: '杭州西湖',
            latitude: 30.2431,
            longitude: 120.1505,
          ),
        ],
      );
      final coordinator = _coordinator(
        gateway: FakeLocationGateway(
          position: const AppGeoPosition(
            latitude: 30.2431,
            longitude: 120.1505,
          ),
        ),
        nearbyReader: query,
        searchReader: query,
      );

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            theme: profile.brightness == Brightness.dark
                ? ThemeData.dark()
                : ThemeData.light(),
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: PublishLocationSelectorPage(locationCoordinator: coordinator),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('杭州西湖'), findsOneWidget);
    });
  }

  testWidgets('权限永久拒绝时展示 locationAppPermissionRequired 文案和去设置按钮', (
    tester,
  ) async {
    final coordinator = _coordinator(
      gateway: FakeLocationGateway(
        permission: LocationPermissionResult.permanentlyDenied,
      ),
      nearbyReader: FakeLocationQueryAdapter(),
    );

    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(375, 812),
        builder: (context, child) => MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: PublishLocationSelectorPage(locationCoordinator: coordinator),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final l10n = AppLocalizationsZh();
    expect(
      find.text(SearchText.recoveryEnablePermissionMessage),
      findsOneWidget,
      reason: '永久拒绝时应展示统一且可执行的权限恢复文案',
    );
    expect(
      find.widgetWithText(CupertinoButton, l10n.locationOpenSettings),
      findsOneWidget,
      reason: '永久拒绝时应展示「去设置」主操作',
    );
  });

  testWidgets('云端错误时展示内联占位和重试按钮', (tester) async {
    final error = CloudException(
      type: CloudErrorType.timeout,
      message: 'timeout',
      statusCode: 504,
      code: IntegrationLocationErrorCode.upstreamTimeout.code,
      runtimeFailure: testRuntimeFailure(
        code: IntegrationLocationErrorCode.upstreamTimeout.code,
        kind: RuntimeFailureKind.timeout,
        nature: RuntimeFailureNature.transient,
      ),
    );
    final coordinator = _coordinator(
      gateway: FakeLocationGateway(
        position: const AppGeoPosition(latitude: 30.65, longitude: 104.06),
      ),
      nearbyReader: FakeLocationQueryAdapter(error: error),
    );

    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(375, 812),
        builder: (context, child) => MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: PublishLocationSelectorPage(locationCoordinator: coordinator),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final errorState = tester.widget<AppPageErrorState>(
      find.byType(AppPageErrorState),
    );
    expect(errorState.semantic.title.trim(), isNotEmpty);
    expect(errorState.semantic.message.trim(), isNotEmpty);
    expect(errorState.semantic.primaryAction?.label, SearchText.reload);
    expect(
      find.widgetWithText(CupertinoButton, SearchText.reload),
      findsOneWidget,
      reason: '非权限错误时应展示内联重试按钮（与错误文案同区）',
    );
  });

  testWidgets('加载态使用统一占位并保留无障碍语义', (tester) async {
    final completer = Completer<LocationPoiListSlice>();
    final pendingReader = _PendingLocationQuery(completer);
    final coordinator = _coordinator(
      gateway: FakeLocationGateway(
        position: const AppGeoPosition(latitude: 30.65, longitude: 104.06),
      ),
      nearbyReader: pendingReader,
      searchReader: pendingReader,
    );

    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(375, 812),
        builder: (context, child) => MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: PublishLocationSelectorPage(locationCoordinator: coordinator),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(AppRequestFeedback), findsOneWidget);
    final feedbackSemantics = tester.widget<Semantics>(
      find.descendant(
        of: find.byType(AppRequestFeedback),
        matching: find.byType(Semantics),
      ),
    );
    expect(
      feedbackSemantics.properties.label,
      FoundationText.loading,
      reason: '占位加载不额外制造可见 spinner，但必须可被读屏识别',
    );
  });
}
