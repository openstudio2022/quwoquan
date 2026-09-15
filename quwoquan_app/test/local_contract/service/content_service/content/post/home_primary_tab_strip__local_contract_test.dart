// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';

Finder tab(String id) => find.byKey(HomePrimaryTabStrip.channelKey(id));
Finder get strip => find.byKey(HomePrimaryTabStrip.stripKey);

Future<void> pumpStrip(
  WidgetTester tester,
  ValueNotifier<String> active, {
  double width = 300,
  double scale = 1,
  bool reduceMotion = false,
  List<HomeChannelConfig>? channels,
}) async {
  await tester.pumpWidget(
    ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: width,
              child: MediaQuery(
                data: MediaQueryData(
                  textScaler: TextScaler.linear(scale),
                  disableAnimations: reduceMotion,
                ),
                child: ValueListenableBuilder<String>(
                  valueListenable: active,
                  builder: (context, id, _) => HomePrimaryTabStrip(
                    activeChannelId: id,
                    onChannelChanged: (id) => active.value = id,
                    isDark: false,
                    channels: channels,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('不溢出切换不移动，默认前缀与 key 保留', (tester) async {
    final active = ValueNotifier('recommend');
    addTearDown(active.dispose);
    await pumpStrip(tester, active, width: 780);
    final before = tester.getCenter(tab('travel'));
    await tester.tap(tab('travel'));
    await tester.pumpAndSettle();
    expect(active.value, 'travel');
    expect(tester.getCenter(tab('travel')), before);
    expect(tab('following').hitTestable(), findsOneWidget);
  });

  testWidgets('越过中点推荐锚定，回首段恢复关注', (tester) async {
    final active = ValueNotifier('recommend');
    addTearDown(active.dispose);
    await pumpStrip(tester, active);
    expect(tab('following').hitTestable(), findsOneWidget);
    active.value = 'travel';
    await tester.pumpAndSettle();
    expect(tester.getRect(tab('recommend')).left, tester.getRect(strip).left);
    expect(tab('following'), findsOneWidget);
    expect(tab('following').hitTestable(), findsNothing);
    expect(
      tester.getCenter(tab('travel')).dx,
      closeTo(tester.getCenter(strip).dx, 0.1),
    );
    await tester.tap(tab('recommend'));
    await tester.pumpAndSettle();
    expect(active.value, 'recommend');
    expect(tab('following').hitTestable(), findsOneWidget);
    expect(
      tester.getRect(tab('recommend')).left,
      greaterThan(tester.getRect(strip).left),
    );
  });

  testWidgets('动画中连续选择最后目标胜出且末项完整可见', (tester) async {
    final active = ValueNotifier('recommend');
    addTearDown(active.dispose);
    await pumpStrip(tester, active);
    await tester.tap(tab('travel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 30));
    await tester.tap(tab('photography'));
    expect(active.value, 'photography');
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    await tester.tap(tab('car'));
    expect(active.value, 'car');
    await tester.pumpAndSettle();
    expect(tab('car').hitTestable(), findsOneWidget);
    expect(
      tester.getRect(tab('car')).right,
      lessThanOrEqualTo(tester.getRect(strip).right + 0.1),
    );
    expect(
      tester.getRect(tab('car')).left,
      greaterThan(tester.getRect(tab('recommend')).right),
    );
    active.value = 'recommend';
    await tester.pump();
    active.value = 'travel';
    await tester.pumpAndSettle();
    expect(
      tester.getCenter(tab('travel')).dx,
      closeTo(tester.getCenter(strip).dx, 0.1),
    );
  });

  testWidgets('标签拖动只滚动并支持反向恢复', (tester) async {
    final active = ValueNotifier('recommend');
    addTearDown(active.dispose);
    await pumpStrip(tester, active);
    await tester.drag(strip, const Offset(-220, 0));
    await tester.pumpAndSettle();
    expect(active.value, 'recommend');
    expect(tester.getRect(tab('recommend')).left, tester.getRect(strip).left);
    await tester.drag(strip, const Offset(500, 0));
    await tester.pumpAndSettle();
    expect(active.value, 'recommend');
    expect(tab('following').hitTestable(), findsOneWidget);
  });

  testWidgets('动态文本缩放与视区变化重算目标，Reduce Motion 即时定位', (tester) async {
    final active = ValueNotifier('travel');
    addTearDown(active.dispose);
    await pumpStrip(tester, active, width: 340, scale: 1.5, reduceMotion: true);
    expect(
      tester.getCenter(tab('travel')).dx,
      closeTo(tester.getCenter(strip).dx, 0.1),
    );
    final beforeWidth = tester.getSize(tab('photography')).width;
    await pumpStrip(tester, active, width: 280, scale: 2, reduceMotion: true);
    expect(tester.getSize(tab('photography')).width, greaterThan(beforeWidth));
    expect(tab('photography').hitTestable(), findsOneWidget);
    active.value = 'car';
    await tester.pump();
    await tester.pump();
    expect(
      tester.getRect(tab('car')).right,
      lessThanOrEqualTo(tester.getRect(strip).right + 0.1),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('配置替换保留真实顺序且移除推荐时不残留锚点', (tester) async {
    final active = ValueNotifier('travel');
    addTearDown(active.dispose);
    await pumpStrip(tester, active);
    final channels = ContentUIConfig.homeChannels
        .where(
          (channel) => channel.id != 'recommend' && channel.id != 'following',
        )
        .toList()
        .reversed
        .toList();
    await pumpStrip(tester, active, channels: channels);
    expect(tab('recommend'), findsNothing);
    final lefts = [
      for (final channel in channels) tester.getRect(tab(channel.id)).left,
    ];
    expect(lefts, orderedEquals([...lefts]..sort()));
    active.value = channels.first.id;
    await tester.pumpAndSettle();
    expect(tab(channels.first.id).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
