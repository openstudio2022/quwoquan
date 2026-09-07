import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/conversation_sheet.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_action_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_entry_sheet.dart';

void main() {
  Finder dragHandleFinder() => find.byWidgetPredicate(
    (widget) =>
        widget is Container &&
        widget.constraints?.minWidth ==
            AppSpacing.createEntrySheetHandleWidth &&
        widget.constraints?.maxWidth ==
            AppSpacing.createEntrySheetHandleWidth &&
        widget.constraints?.minHeight ==
            AppSpacing.createEntrySheetHandleHeight &&
        widget.constraints?.maxHeight ==
            AppSpacing.createEntrySheetHandleHeight,
    description: 'sheet drag handle',
  );

  testWidgets('加号入口首层内容优先，更多不包含活动', (tester) async {
    EditorStartAction? selected;
    var groupChatTapped = false;

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
                onStartGroupChat: () => groupChatTapped = true,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
    expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);
    expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
    expect(find.byKey(TestKeys.createActionMore), findsOneWidget);
    expect(find.text('发起活动'), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsNothing);

    expect(find.text(CreationText.createActionAddContactShort), findsNothing);
    expect(find.text(CreationText.createActionCreateCircleShort), findsNothing);
    // 「交集配对」launcher 与「发起活动」直达入口均已退役（intersection-unified-experience REQ-005）。
    expect(find.text('交集配对'), findsNothing);
    expect(find.text(FoundationText.cancel), findsOneWidget);
    expect(find.byType(ConversationSheetListCard), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);
    expect(
      find.descendant(
        of: find.byKey(TestKeys.modalBottomSheetPanel),
        matching: find.byType(Icon),
      ),
      findsNothing,
    );
    expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
    expect(find.byType(ConversationSheetCancelBar), findsOneWidget);
    expect(dragHandleFinder(), findsOneWidget);
    expect(
      tester.getTopLeft(find.byKey(TestKeys.modalBottomSheetPanel)).dy,
      greaterThan(0),
    );

    await tester.tap(find.byKey(TestKeys.createActionCapture));
    await tester.pump();
    expect(selected, EditorStartAction.video);

    await tester.tap(find.byKey(TestKeys.createActionMore));
    await tester.pump();
    expect(find.text('发起活动'), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createActionStartGroupChat));
    await tester.pump();
    expect(groupChatTapped, isTrue);
  });

  testWidgets('Android 与 iOS 均渲染同一套列表式加号面板', (tester) async {
    try {
      for (final platform in <TargetPlatform>[
        TargetPlatform.iOS,
        TargetPlatform.android,
      ]) {
        debugDefaultTargetPlatformOverride = platform;

        await tester.pumpWidget(
          ProviderScope(
            child: ScreenUtilInit(
              designSize: const Size(390, 844),
              builder: (context, child) => MaterialApp(
                home: Scaffold(
                  body: CreateEntrySheet(
                    isOpen: true,
                    onClose: () {},
                    onSelect: (_) {},
                    onStartGroupChat: () {},
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
        expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);
        expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
        expect(find.byKey(TestKeys.createActionMore), findsOneWidget);
        expect(find.text('发起活动'), findsNothing);
        expect(find.byKey(TestKeys.createActionStartGroupChat), findsNothing);
        expect(
          find.descendant(
            of: find.byKey(TestKeys.modalBottomSheetPanel),
            matching: find.byType(Icon),
          ),
          findsNothing,
        );
        expect(find.byType(ConversationSheetListCard), findsOneWidget);

        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
      }
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('深色模式下创作入口顶部仅渲染一个标准拖拽手柄', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: CupertinoTheme(
              data: const CupertinoThemeData(brightness: Brightness.dark),
              child: Scaffold(
                body: CreateEntrySheet(
                  isOpen: true,
                  onClose: () {},
                  onSelect: (_) {},
                  onStartGroupChat: () {},
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(dragHandleFinder(), findsOneWidget);
    final handle = tester.widget<Container>(dragHandleFinder());
    final decoration = handle.decoration! as BoxDecoration;
    expect(
      decoration.color,
      AppColorsFunctional.getColor(true, ColorType.separatorOpaque),
    );
  });

  testWidgets('内容创作固定为照片视频文字顺序', (tester) async {
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
                onStartGroupChat: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final galleryY = tester
        .getCenter(find.byKey(TestKeys.createActionGallery))
        .dy;
    final cameraY = tester
        .getCenter(find.byKey(TestKeys.createActionCapture))
        .dy;
    final writeY = tester.getCenter(find.byKey(TestKeys.createActionWrite)).dy;
    expect(galleryY, lessThan(cameraY));
    expect(cameraY, lessThan(writeY));
  });

  testWidgets('移动端更多仅承接普通群聊，不暴露无上下文活动', (tester) async {
    var groupChatTapped = false;

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateActionSheet(
                onCreateAction: (_) {},
                onStartGroupChat: () => groupChatTapped = true,
                onCancel: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('发起活动'), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsNothing);
    await tester.tap(find.byKey(TestKeys.createActionMore));
    await tester.pump();
    expect(find.text('发起活动'), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsOneWidget);
    await tester.tap(find.byKey(TestKeys.createActionStartGroupChat));
    await tester.pump();
    expect(groupChatTapped, isTrue);
  });

  testWidgets('iPad 下发起弹窗保持内容驱动高度', (tester) async {
    tester.view.physicalSize = const Size(1024, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(1024, 768),
          builder: (context, child) => MaterialApp(
            home: Scaffold(
              body: CreateActionSheet(
                onCreateAction: (_) {},
                onStartGroupChat: () {},
                onCancel: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    expect(panel, findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(120));
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
                onStartGroupChat: () {},
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
