import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  testWidgets('关闭 create action entry flag 后回退到旧版创作入口', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentFeatureFlagProvider(
            'enable_create_action_entry',
          ).overrideWith((ref) => false),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (context, _) => MaterialApp(
            home: Scaffold(
              body: CreateEntrySheet(
                isOpen: true,
                onClose: () {},
                onSelect: (_) {},
                onOpenLegacyTab: (_) {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('发点滴'), findsOneWidget);
    expect(find.text('发图片'), findsOneWidget);
    expect(find.text('发视频'), findsOneWidget);
    expect(find.text('写笔记'), findsOneWidget);

    expect(find.text('从相册选'), findsNothing);
    expect(find.text('写点什么'), findsNothing);
    expect(find.text('拍一下'), findsNothing);
  });
}
