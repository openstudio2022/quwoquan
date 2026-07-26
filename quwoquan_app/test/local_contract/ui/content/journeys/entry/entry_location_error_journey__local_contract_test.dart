// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-001
/// L1c Journey Test: 创作→选位置→云端超时→统一全屏页态错误
///
/// 规范：specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md
/// 决策：进入选位置页即首屏加载失败、无任何可展示内容 → 全屏 emptyPage（AppPageErrorState）。
/// 页态类别为 pageLoad，按 `ui_error_semantics` 统一为通用标题/说明，不泄漏领域技术文案。
/// 特性树：cloud-network-error-display-contract
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../support/fake_location_gateway.dart';
import '../../../../../support/fake_location_readers.dart';
import '../../../../../support/runtime_failure_fixtures.dart';

void main() {
  testWidgets('创作入口→选位置→云端超时→展示统一全屏页态错误和重试', (tester) async {
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
    final locationQuery = FakeLocationQueryAdapter(error: error);
    final coordinator = CreateLocationCoordinator(
      nearbyReader: locationQuery,
      searchReader: locationQuery,
      locationGateway: FakeLocationGateway(
        position: const AppGeoPosition(latitude: 30.65, longitude: 104.06),
      ),
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
                onPressed: () =>
                    Navigator.of(
                      tester.element(find.byType(Scaffold)),
                    ).push<void>(
                      CupertinoPageRoute<void>(
                        builder: (_) => PublishLocationSelectorPage(
                          locationCoordinator: coordinator,
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

    // pageLoad 类别（首屏无内容）统一走全屏 AppPageErrorState，
    // 标题/说明为通用文案，而非领域专用的 locationUpstreamTimeout 内联文案。
    expect(
      find.text(UITextConstants.pageLoadFailedTitle),
      findsOneWidget,
      reason: '云端超时首屏失败应展示统一全屏页态标题',
    );
    expect(
      find.text(UITextConstants.pageLoadFailedMessage),
      findsOneWidget,
      reason: 'pageLoad 类别 timeout 走统一页态说明文案，不泄漏领域技术文案',
    );
    expect(
      find.widgetWithText(CupertinoButton, UITextConstants.tryAgain),
      findsOneWidget,
      reason: '应展示统一页态重试主操作',
    );
  });
}
