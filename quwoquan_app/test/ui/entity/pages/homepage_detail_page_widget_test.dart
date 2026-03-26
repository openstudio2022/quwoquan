import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';

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

  testWidgets('主页详情页展示壳层摘要与 contextual publish 入口', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: HomepageDetailPage(homepageId: 'homepage_sight_west_lake'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('西湖景区'), findsWidgets);
    expect(find.text('概览'), findsOneWidget);
    expect(find.text('内容'), findsWidgets);
    expect(find.text('关联'), findsOneWidget);
    expect(find.text('认领主页'), findsWidgets);
    expect(find.text('治理入口'), findsNothing);
  });

  testWidgets('选择模式显示 attach 按钮', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: HomepageDetailPage(
            homepageId: 'homepage_sight_west_lake',
            selectionMode: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('关联到本次发布'), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
