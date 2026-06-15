import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

Widget _buildApp(Widget child) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: child),
      ),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 8}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

class _DiscoveryIdentityRailPreview extends StatelessWidget {
  const _DiscoveryIdentityRailPreview();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: ContentUIConfig.discoveryRails
          .map(
            (rail) => Text(UITextConstants.contentLabelForKey(rail.labelKey)),
          )
          .toList(growable: false),
    );
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('发现页双轨标签固定为点滴/作品且不再暴露微趣', (tester) async {
    await tester.pumpWidget(_buildApp(const _DiscoveryIdentityRailPreview()));
    await tester.pump();

    expect(find.text('点滴'), findsAtLeastNWidgets(1));
    expect(find.text('作品'), findsAtLeastNWidgets(1));
    expect(find.text('微趣'), findsNothing);
  });

  testWidgets('作品频道格式筛选使用全部作品/图片/视频/文章（V1.0 经更多面板暴露）', (tester) async {
    // V1.0：媒体筛选不再以顶部 tab 常驻，由「更多」面板内的筛选 chips 暴露；
    // 此处校验筛选配置真相源的标签集合保持全部/图片/视频/文章。
    await tester.pumpWidget(
      _buildApp(
        Row(
          children: ContentUIConfig.workFormatFilters
              .map(
                (filter) =>
                    Text(UITextConstants.contentLabelForKey(filter.labelKey)),
              )
              .toList(growable: false),
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('全部作品'), findsAtLeastNWidgets(1));
    expect(find.text('图片'), findsAtLeastNWidgets(1));
    expect(find.text('视频'), findsAtLeastNWidgets(1));
    expect(find.text('文章'), findsAtLeastNWidgets(1));
    expect(find.text('笔记'), findsNothing);
  });
}
