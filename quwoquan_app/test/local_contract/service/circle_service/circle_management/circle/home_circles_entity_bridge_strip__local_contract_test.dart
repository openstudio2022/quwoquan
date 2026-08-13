// 首页圈子「地点和事物」实体桥接条契约：三张类型卡完整渲染（标题+引导语），
// 点击卡片携带该类型搜索词回调（圈子↔实体发现桥，交集主线拼图入口）。
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/spec.md#sit-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/home_circles_entity_bridge_strip.dart';

Future<void> _pump(WidgetTester tester, List<String> taps) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: HomeCirclesEntityBridgeStrip(
            isDark: false,
            onEntityTap: taps.add,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('桥接条渲染标题与三张实体类型卡', (tester) async {
    await _pump(tester, <String>[]);

    expect(find.text(CommunityText.circlesEntitySectionTitle), findsOneWidget);
    expect(find.text(CommunityText.circlesEntitySectionHint), findsOneWidget);
    expect(find.text(CreationText.homepageTypeUniversity), findsOneWidget);
    expect(find.text(CreationText.homepageTypeTravelPhoto), findsOneWidget);
    expect(find.text(CreationText.homepageTypeHotel), findsOneWidget);
  });

  testWidgets('点击类型卡携带该类型搜索词回调', (tester) async {
    final taps = <String>[];
    await _pump(tester, taps);

    await tester.tap(find.text(CreationText.homepageTypeUniversity));
    await tester.pumpAndSettle();

    expect(taps, <String>[CreationText.homepageTypeUniversity]);
  });
}
