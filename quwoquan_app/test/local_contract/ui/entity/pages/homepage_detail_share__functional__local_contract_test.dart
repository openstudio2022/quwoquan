import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_repository_mock.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_share_sheet.dart';

/// GWT（homepage-entry-and-preview 分享分发面）：
/// - Given 已发布主页详情，When 点击顶栏分享，Then 打开统一转发面板
///   （链接/深链由 metadata link 模板 codegen 提供，无第二套 URL 真相源）。
/// - more 菜单同样提供「分享主页」入口。
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

  Widget buildApp() {
    return ProviderScope(
      overrides: [
        homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
        homepageIntroductionRepositoryProvider.overrideWithValue(
          const MockHomepageIntroductionRepository(),
        ),
      ],
      child: const MaterialApp(
        home: HomepageDetailPage(homepageId: 'homepage_sight_west_lake'),
      ),
    );
  }

  testWidgets('已发布主页点击顶栏分享打开统一转发面板', (tester) async {
    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    final shareButton = find.byKey(
      const ValueKey<String>('object-chrome-share'),
    );
    expect(shareButton, findsOneWidget);
    await tester.tap(shareButton);
    await tester.pumpAndSettle();

    expect(find.byType(ForwardShareSheet), findsOneWidget);
    expect(find.text(ChatText.forwardMostContacted), findsOneWidget);
  });

  testWidgets('更多菜单包含分享主页动作并打开统一转发面板', (tester) async {
    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    final moreButton = find.byKey(const ValueKey<String>('object-chrome-more'));
    expect(moreButton, findsOneWidget);
    await tester.tap(moreButton);
    await tester.pumpAndSettle();

    final shareAction = find.text(UITextConstants.homepageShareAction);
    expect(shareAction, findsOneWidget);
    await tester.tap(shareAction);
    await tester.pumpAndSettle();

    expect(find.byType(ForwardShareSheet), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
