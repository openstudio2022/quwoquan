// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-008

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
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

    expect(find.text(UITextConstants.whoCanSeeLabel), findsOneWidget);
    expect(find.text(UITextConstants.locationLabel), findsOneWidget);
    expect(find.text(UITextConstants.attachHomepageTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.selectPublishCirclesLabel),
      findsOneWidget,
    );
  });

  testWidgets('已移除内容摘要/标签/关联地点和事物/小趣推荐/小趣使用/圈子内形式/内容概览', (tester) async {
    await _openSheet(tester);

    // 已删区块标题不得再出现，确保发布页保持整洁。
    expect(find.text('内容摘要'), findsNothing);
    expect(find.text('AI 摘要'), findsNothing);
    expect(find.text('标签'), findsNothing);
    expect(find.text('关联地点和事物'), findsNothing);
    expect(
      find.text(UITextConstants.publishAssistantSuggestTitle),
      findsNothing,
    );
    expect(find.text('小趣使用'), findsNothing);
    expect(find.text('内容概览'), findsNothing);
    expect(find.text(UITextConstants.circlePublishModeLabel), findsNothing);
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
      find.text(UITextConstants.createPublishCirclesUnavailable),
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

    await tester.tap(find.text(UITextConstants.whoCanSeeLabel));
    await tester.pumpAndSettle();
    // 动作面板出现：选中「私密」选项后点确认。
    await tester.tap(find.text(UITextConstants.visibilityPrivate).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.confirm));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createPublishConfirmButton));
    await tester.pumpAndSettle();

    expect(confirmed, isNotNull);
    expect(confirmed!.isPublic, isFalse);
  });
}
