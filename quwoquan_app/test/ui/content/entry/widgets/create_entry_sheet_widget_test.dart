import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  testWidgets('创作入口收口为三动作入口', (tester) async {
    EditorStartAction? selected;

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateEntrySheet(
                isOpen: true,
                onClose: () {},
                onSelect: (action) => selected = action,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('创作'), findsNothing);
    expect(find.text('连接'), findsNothing);
    expect(find.text('从相册选择'), findsOneWidget);
    expect(find.text('写文字'), findsOneWidget);
    expect(find.text('相机'), findsOneWidget);
    expect(find.text('发起群聊'), findsOneWidget);
    expect(find.text('添加同好'), findsOneWidget);
    expect(find.text('取消'), findsOneWidget);
    expect(find.text('作品'), findsNothing);
    expect(find.text('文章'), findsNothing);
    expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
    expect(
      tester.getTopLeft(find.byKey(TestKeys.modalBottomSheetPanel)).dy,
      greaterThan(0),
    );

    await tester.tap(find.text('相机'));
    await tester.pump();

    expect(selected, EditorStartAction.capture);
  });

  testWidgets('趣信上下文优先突出连接动作组', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateEntrySheet(
                isOpen: true,
                onClose: () {},
                onSelect: (_) {},
                priority: CreateActionSheetPriority.socialPrimary,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final groupChatY = tester.getCenter(find.text('发起群聊')).dy;
    final galleryY = tester.getCenter(find.text('从相册选择')).dy;
    expect(groupChatY, lessThan(galleryY));
  });

  testWidgets('社交动作组支持新建圈子入口', (tester) async {
    var createCircleTapped = false;

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateActionSheet(
                onCreateAction: (_) {},
                onStartGroupChat: () {},
                onAddContact: () {},
                onCreateCircle: () => createCircleTapped = true,
                onCancel: () {},
                priority: CreateActionSheetPriority.socialPrimary,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('创建圈子'), findsOneWidget);

    await tester.tap(find.text('创建圈子'));
    await tester.pump();

    expect(createCircleTapped, isTrue);
  });

  testWidgets('点击上半区空白区域可关闭全屏弹层', (tester) async {
    var closed = false;

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateEntrySheet(
                isOpen: true,
                onClose: () => closed = true,
                onSelect: (_) {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tapAt(const Offset(20, 20));
    await tester.pump();

    expect(closed, isTrue);
  });
}
