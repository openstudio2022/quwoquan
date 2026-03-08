import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/fake_location_permission_checker.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/l10n/app_localizations_zh.dart';

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient(this.handler) : super(client: http.Client());
  final Future<dynamic> Function(Uri uri, Map<String, String> headers) handler;

  @override
  Future<dynamic> getJson(Uri uri, {required Map<String, String> headers}) =>
      handler(uri, headers);
}

Position _fakePosition() => Position(
      latitude: 30.65,
      longitude: 104.06,
      timestamp: DateTime.now(),
      accuracy: 0,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );

/// L1b Widget 测试：位置选择页权限永久拒绝 → 展示 locationAppPermissionRequired + 去设置
///
/// 规范：specs/ux/error-and-permission-semantics.md
/// 特性树：permission-card-display-contract
void main() {
  testWidgets(
    '权限永久拒绝时展示 locationAppPermissionRequired 文案和去设置按钮',
    (tester) async {
      final checker = FakeLocationPermissionChecker(
        result: LocationPermissionResult.permanentlyDenied,
        position: null,
      );
      final locationService = CreateLocationService(
        locationPermissionChecker: checker,
      );

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: PublishLocationSelectorPage(
              locationService: locationService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final l10n = AppLocalizationsZh();
      expect(
        find.text(l10n.locationAppPermissionRequired),
        findsOneWidget,
        reason: '永久拒绝时应展示 locationAppPermissionRequired 文案',
      );
      expect(
        find.widgetWithText(CupertinoButton, l10n.locationOpenSettings),
        findsOneWidget,
        reason: '永久拒绝时应展示「去设置」主操作',
      );
    },
  );

  testWidgets(
    '云端错误时展示内联占位和重试按钮',
    (tester) async {
      final checker = FakeLocationPermissionChecker(
        result: LocationPermissionResult.granted,
        position: _fakePosition(),
      );
      final httpClient = _StubCloudHttpClient((uri, headers) async {
        throw CloudException(
          type: CloudErrorType.timeout,
          message: 'timeout',
          statusCode: 504,
          code: IntegrationLocationErrorCode.upstreamTimeout.code,
        );
      });
      final locationService = CreateLocationService(
        locationPermissionChecker: checker,
        httpClient: httpClient,
        baseUrl: 'http://test',
      );

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: PublishLocationSelectorPage(
              locationService: locationService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final l10n = AppLocalizationsZh();
      expect(
        find.text(l10n.locationUpstreamTimeout),
        findsOneWidget,
        reason: '云端超时应展示 locationUpstreamTimeout 文案',
      );
      expect(
        find.widgetWithText(CupertinoButton, l10n.retry),
        findsOneWidget,
        reason: '非权限错误时应展示内联重试按钮（与错误文案同区）',
      );
    },
  );

  testWidgets(
    '加载态展示 locationFetchingResult',
    (tester) async {
      final completer = Completer<Map<String, dynamic>>();
      final checker = FakeLocationPermissionChecker(
        result: LocationPermissionResult.granted,
        position: _fakePosition(),
      );
      final httpClient = _StubCloudHttpClient((uri, headers) async {
        if (uri.path == IntegrationLocationMetadata.nearbyPath) return completer.future;
        return {IntegrationLocationMetadata.responseItemsKey: []};
      });
      final locationService = CreateLocationService(
        locationPermissionChecker: checker,
        httpClient: httpClient,
        baseUrl: 'http://test',
      );

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: PublishLocationSelectorPage(
              locationService: locationService,
            ),
          ),
        ),
      );
      await tester.pump();
      final l10n = AppLocalizationsZh();
      expect(
        find.text(l10n.locationFetchingResult),
        findsOneWidget,
        reason: '加载时应展示 locationFetchingResult',
      );
    },
  );
}
