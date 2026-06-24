import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  Icon iconFor(WidgetTester tester, IconData icon) =>
      tester.widget<Icon>(find.byIcon(icon));
  Finder dragHandleFinder() => find.byWidgetPredicate(
    (widget) =>
        widget is Container &&
        widget.constraints?.minWidth == AppSpacing.createEntrySheetHandleWidth &&
        widget.constraints?.maxWidth == AppSpacing.createEntrySheetHandleWidth &&
        widget.constraints?.minHeight ==
            AppSpacing.createEntrySheetHandleHeight &&
        widget.constraints?.maxHeight ==
            AppSpacing.createEntrySheetHandleHeight,
    description: 'sheet drag handle',
  );

  testWidgets('创作入口收口为图片/视频/长文/续草稿', (tester) async {
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
                onContinueFromDraft: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('创作'), findsNothing);
    expect(find.text('连接'), findsNothing);
    expect(
      find.text(UITextConstants.createActionPostPhotoShort),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.createActionWriteLong), findsOneWidget);
    expect(
      find.text(UITextConstants.createActionPostVideoShort),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.createActionResumeDraft), findsOneWidget);
    expect(
      find.text(UITextConstants.createActionCreateGroupShort),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionAddContactShort),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.cancel), findsOneWidget);
    expect(
      tester
          .getCenter(find.text(UITextConstants.createActionPostPhotoShort))
          .dx,
      lessThan(
        tester
            .getCenter(find.text(UITextConstants.createActionPostVideoShort))
            .dx,
      ),
    );
    expect(
      tester
          .getCenter(find.text(UITextConstants.createActionPostVideoShort))
          .dx,
      lessThan(
        tester.getCenter(find.text(UITextConstants.createActionWriteLong)).dx,
      ),
    );
    expect(
      tester.getCenter(find.text(UITextConstants.createActionWriteLong)).dx,
      lessThan(
        tester.getCenter(find.text(UITextConstants.createActionResumeDraft)).dx,
      ),
    );
    expect(find.text('作品'), findsNothing);
    expect(find.text('文章'), findsNothing);
    expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
    expect(find.byType(ConversationSheetCancelBar), findsOneWidget);
    expect(dragHandleFinder(), findsOneWidget);
    expect(
      tester.getTopLeft(find.byKey(TestKeys.modalBottomSheetPanel)).dy,
      greaterThan(0),
    );

    await tester.tap(find.text(UITextConstants.createActionPostVideoShort));
    await tester.pump();

    expect(selected, EditorStartAction.capture);
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
                  onContinueFromDraft: () {},
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
                onContinueFromDraft: () {},
                priority: CreateActionSheetPriority.socialPrimary,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final discussionY = tester
        .getCenter(find.text(UITextConstants.createActionCreateGroupShort))
        .dy;
    final galleryY = tester
        .getCenter(find.text(UITextConstants.createActionPostPhotoShort))
        .dy;
    expect(discussionY, lessThan(galleryY));
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
                onContinueFromDraft: () {},
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

    expect(
      find.text(UITextConstants.createActionCreateCircleShort),
      findsOneWidget,
    );
    expect(find.byIcon(FluentIcons.image_add_24_regular), findsOneWidget);
    expect(find.byIcon(FluentIcons.video_add_24_regular), findsOneWidget);
    expect(find.byIcon(FluentIcons.document_edit_24_regular), findsOneWidget);
    expect(
      find.byIcon(FluentIcons.document_text_clock_24_regular),
      findsOneWidget,
    );
    expect(find.byIcon(FluentIcons.person_add_24_regular), findsOneWidget);
    expect(find.byIcon(FluentIcons.chat_multiple_24_regular), findsOneWidget);
    expect(
      find.byIcon(FluentIcons.people_add_24_regular),
      findsOneWidget,
    );
    expect(
      iconFor(tester, FluentIcons.image_add_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.video_add_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.document_edit_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.document_text_clock_24_regular).color,
      SettingsSemanticConstants.createSheetDraftActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.person_add_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.chat_multiple_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );
    expect(
      iconFor(tester, FluentIcons.people_add_24_regular).color,
      SettingsSemanticConstants.createSheetActionIconColor(false),
    );

    await tester.tap(find.text(UITextConstants.createActionCreateCircleShort));
    await tester.pump();

    expect(createCircleTapped, isTrue);
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
                onContinueFromDraft: () {},
                onStartGroupChat: () {},
                onAddContact: () {},
                onCancel: () {},
                priority: CreateActionSheetPriority.socialPrimary,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    expect(panel, findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(240));
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
                onContinueFromDraft: () {},
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
