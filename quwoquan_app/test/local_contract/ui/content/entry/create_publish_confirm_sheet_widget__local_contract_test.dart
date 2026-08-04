// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-008

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/content/media/media_upload_session/domain/media_capture_metadata.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_publish_confirm_sheet.dart';
import '../../../../support/fake_location_gateway.dart';
import '../../../../support/fake_location_readers.dart';

CreateLocationCoordinator _locationCoordinator() {
  final query = FakeLocationQueryAdapter();
  return CreateLocationCoordinator(
    nearbyReader: query,
    searchReader: query,
    locationGateway: FakeLocationGateway(),
  );
}

Widget _buildApp({
  PublishSettings initialSettings = const PublishSettings(),
  ValueChanged<PublishSettings>? onConfirm,
  bool circleLoadUnavailable = false,
}) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => CupertinoApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: _Host(
          initialSettings: initialSettings,
          onConfirm: onConfirm,
          circleLoadUnavailable: circleLoadUnavailable,
        ),
      ),
    ),
  );
}

class _Host extends StatelessWidget {
  const _Host({
    required this.initialSettings,
    this.onConfirm,
    required this.circleLoadUnavailable,
  });

  final PublishSettings initialSettings;
  final ValueChanged<PublishSettings>? onConfirm;
  final bool circleLoadUnavailable;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      child: Center(
        child: CupertinoButton(
          child: const Text('打开发布确认'),
          onPressed: () async {
            final result = await Navigator.of(context).push<PublishSettings>(
              CupertinoPageRoute<PublishSettings>(
                builder: (_) => CreatePublishConfirmSheet(
                  initialSettings: initialSettings,
                  locationCoordinator: _locationCoordinator(),
                  joinedCircles: const <CreateCircleOption>[],
                  recommendedCircles: const <CreateCircleOption>[],
                  circleLoadUnavailable: circleLoadUnavailable,
                ),
              ),
            );
            if (result != null) {
              onConfirm?.call(result);
            }
          },
        ),
      ),
    );
  }
}

Future<void> _openSheet(WidgetTester tester) async {
  await tester.pumpWidget(_buildApp());
  await tester.pumpAndSettle();
  await tester.tap(find.text('打开发布确认'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('仅渲染四项核心设置：谁可以看 / 所在位置 / 关联主页 / 发布到圈子', (tester) async {
    await _openSheet(tester);

    expect(find.text(CreationText.whoCanSeeLabel), findsOneWidget);
    expect(find.text(CreationText.locationLabel), findsOneWidget);
    expect(find.text(CreationText.attachHomepageTitle), findsOneWidget);
    expect(find.text(CreationText.selectPublishCirclesLabel), findsOneWidget);
  });

  testWidgets('已移除内容摘要/标签/关联地点和事物/小趣推荐/小趣使用/圈子内形式/内容概览', (tester) async {
    await _openSheet(tester);

    // 已删区块标题不得再出现，确保发布页保持整洁。
    expect(find.text('内容摘要'), findsNothing);
    expect(find.text('AI 摘要'), findsNothing);
    expect(find.text('标签'), findsNothing);
    expect(find.text('关联地点和事物'), findsNothing);
    expect(
      find.text(ObjectHomepageText.publishAssistantSuggestTitle),
      findsNothing,
    );
    expect(find.text('小趣使用'), findsNothing);
    expect(find.text('内容概览'), findsNothing);
    expect(find.text(CreationText.circlePublishModeLabel), findsNothing);
    // 已删区块对应的 TestKey 控件也不应存在。
    expect(find.byKey(TestKeys.createPublishSummaryField), findsNothing);
    expect(find.byKey(TestKeys.createPublishTagInput), findsNothing);
    expect(find.byKey(TestKeys.createPublishEntityInput), findsNothing);
    expect(
      find.byKey(TestKeys.createPublishAssistantSuggestButton),
      findsNothing,
    );
  });

  testWidgets('确认发布返回初始设置，不再注入/编辑摘要', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(onConfirm: (settings) => confirmed = settings),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.summary, isEmpty);
  });

  testWidgets('圈子查询不可用时展示明确降级且仍可公开发布', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        circleLoadUnavailable: true,
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    expect(
      find.text(CreationText.createPublishCirclesUnavailable),
      findsOneWidget,
    );
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.circleIds, isEmpty);
    expect(confirmed!.isPublic, isTrue);
  });

  testWidgets('切换可见性为私密后确认返回 isPublic=false', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(onConfirm: (settings) => confirmed = settings),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    await tester.tap(find.text(CreationText.whoCanSeeLabel));
    await tester.pumpAndSettle();
    // 动作面板出现：选中「私密」选项后点确认。
    await tester.tap(find.text(CreationText.visibilityPrivate).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text(FoundationText.confirm));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.isPublic, isFalse);
  });

  testWidgets('未绑定地点时不展示出行时间入口', (tester) async {
    await _openSheet(tester);

    expect(find.text(CreationText.visitedAtLabel), findsNothing);
  });

  testWidgets('绑定地点后可声明出行时间，且不可选未来日期', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        initialSettings: _placeAnchoredSettings,
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    expect(find.text(CreationText.visitedAtLabel), findsOneWidget);
    expect(find.text(CreationText.visitedAtUndeclared), findsOneWidget);

    await tester.tap(find.text(CreationText.visitedAtLabel));
    await tester.pumpAndSettle();

    final picker = tester.widget<CupertinoDatePicker>(
      find.byKey(const ValueKey<String>('publish-confirm-visited-at-picker')),
    );
    final today = DateTime.now();
    expect(
      picker.maximumDate,
      DateTime(today.year, today.month, today.day),
      reason: '未来日期是出行计划，不是到访事实',
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('publish-confirm-visited-at-confirm')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.visitedAt, isNotNull);
    expect(
      confirmed!.toPayloadFields()['visitedAt'],
      isNotNull,
      reason: '声明后的到访时间必须进入发布 payload',
    );
  });

  testWidgets('已声明的出行时间可清除，清除后不进入 payload', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        initialSettings: _placeAnchoredSettings.copyWith(
          visitedAt: DateTime(2026, 4, 5),
        ),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    expect(find.text('2026-04-05'), findsOneWidget);

    await tester.tap(find.text(CreationText.visitedAtLabel));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('publish-confirm-visited-at-clear')),
    );
    await tester.pumpAndSettle();

    expect(find.text(CreationText.visitedAtUndeclared), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.visitedAt, isNull);
    expect(confirmed!.toPayloadFields().containsKey('visitedAt'), isFalse);
  });

  testWidgets('只展示实际解析到的拍摄信息分组，关闭后不再进入披露闭集', (tester) async {
    PublishSettings? confirmed;
    await tester.pumpWidget(
      _buildApp(
        initialSettings: const PublishSettings(
          captureMetadata: ExtractedMediaCaptureMetadata(
            cameraModel: 'ILCE-7M4',
            isoSensitivity: 800,
          ),
          captureDisclosure: <CaptureMetadataDisclosureGroup>{
            CaptureMetadataDisclosureGroup.gear,
            CaptureMetadataDisclosureGroup.parameters,
          },
        ),
        onConfirm: (settings) => confirmed = settings,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('打开发布确认'));
    await tester.pumpAndSettle();

    expect(find.text(CreationText.captureDisclosureLabel), findsOneWidget);
    expect(find.text('2/2 项已开启'), findsOneWidget);
    await tester.tap(find.text(CreationText.captureDisclosureLabel));
    await tester.pumpAndSettle();
    expect(find.text(CreationText.captureDisclosurePlace), findsNothing);
    expect(find.text(CreationText.captureDisclosureTime), findsNothing);
    await tester.tap(find.text(CreationText.captureDisclosureGear));
    await tester.pump();
    await tester.tap(find.text(CreationText.visitedAtConfirm));
    await tester.pumpAndSettle();
    expect(find.text('1/2 项已开启'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();
    expect(confirmed?.captureDisclosure, <CaptureMetadataDisclosureGroup>{
      CaptureMetadataDisclosureGroup.parameters,
    });
  });
}

/// 已选位置并解析出行政区标签的发布设置，是出行时间入口的前置条件。
const PublishSettings _placeAnchoredSettings = PublishSettings(
  locationName: '老君山观景台',
  geoTagRef: 'Topic/地理/行政区/河南省/洛阳市',
);
