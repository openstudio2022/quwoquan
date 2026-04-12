/// L1c Journey Test: 创作→选位置→云端超时→内联错误
///
/// 规范：specs/ux/error-and-permission-semantics.md
/// 特性树：cloud-network-error-display-contract
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/fake_location_permission_checker.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/l10n/app_localizations_zh.dart';

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient(this.handler) : super(client: http.Client());
  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
  ) handler;

  @override
  Future<CloudHttpDecodedJson> getJson(
    Uri uri, {
    required Map<String, String> headers,
  }) =>
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

void main() {
  testWidgets(
    '创作入口→选位置→云端超时→展示内联错误和重试',
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
            home: Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () => Navigator.of(
                    tester.element(find.byType(Scaffold)),
                  ).push<void>(
                    CupertinoPageRoute<void>(
                      builder: (_) => PublishLocationSelectorPage(
                        locationService: locationService,
                      ),
                    ),
                  ),
                  child: const Text('选位置'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('选位置'));
      await tester.pumpAndSettle();

      final l10n = AppLocalizationsZh();
      expect(
        find.text(l10n.locationUpstreamTimeout),
        findsOneWidget,
        reason: '云端超时应展示内联错误占位',
      );
      expect(
        find.widgetWithText(CupertinoButton, l10n.retry),
        findsOneWidget,
        reason: '应展示内联重试按钮（与错误文案同区）',
      );
    },
  );
}
