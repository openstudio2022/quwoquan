import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/content/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/content/content/post/presentation/create_action_sheet.dart';
import 'package:quwoquan_app/content/content/post/presentation/create_entry_sheet.dart';

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

  testWidgets('加号入口保留三项创作和四项社交动作', (tester) async {
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

    expect(
      find.text(CreationText.createActionPublishGroupTitle),
      findsNothing,
    );
    expect(
      find.text(CreationText.createActionSocialGroupTitle),
      findsNothing,
    );
    expect(
      find.text(CreationText.createActionPostPhotoShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionPhotoSubtitle),
      findsOneWidget,
    );
    expect(find.text(CreationText.createActionWriteLong), findsOneWidget);
    expect(
      find.text(CreationText.createActionPostVideoShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionCameraSubtitle),
      findsOneWidget,
    );
    expect(find.text(CreationText.createActionResumeDraft), findsNothing);
    expect(find.text(ChatText.createActionCreateGroupShort), findsOneWidget);
    expect(
      find.text(CreationText.createActionAddContactShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionCreateCircleShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionInterestMatchShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionInterestMatchSubtitle),
      findsOneWidget,
    );
    expect(find.text('发图片'), findsNothing);
    expect(find.text('发视频'), findsNothing);
    expect(find.text('写长文'), findsNothing);
    expect(find.text('续草稿'), findsNothing);
    expect(find.text('加联系'), findsNothing);
    expect(find.text('建圈子'), findsNothing);
    expect(find.text(FoundationText.cancel), findsOneWidget);
    expect(find.byKey(TestKeys.createActionContinueFromDraft), findsNothing);
    expect(find.byType(ConversationSheetListCard), findsNWidgets(2));
    expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);
    expect(
      find.descendant(
        of: find.byKey(TestKeys.modalBottomSheetPanel),
        matching: find.byType(Icon),
      ),
      findsNothing,
    );
    expect(
      tester
          .getCenter(find.text(CreationText.createActionPostPhotoShort))
          .dy,
      lessThan(
        tester
            .getCenter(find.text(CreationText.createActionPostVideoShort))
            .dy,
      ),
    );
    expect(
      tester
          .getCenter(find.text(CreationText.createActionPostVideoShort))
          .dy,
      lessThan(
        tester.getCenter(find.text(CreationText.createActionWriteLong)).dy,
      ),
    );
    expect(
      tester.getCenter(find.text(CreationText.createActionWriteLong)).dy,
      greaterThan(
        tester
            .getCenter(find.text(CreationText.createActionPostVideoShort))
            .dy,
      ),
    );
    expect(
      tester.getCenter(find.text(CreationText.createActionWriteLong)).dy,
      lessThan(
        tester
            .getCenter(find.text(CreationText.createActionAddContactShort))
            .dy,
      ),
    );
    expect(
      tester
          .getCenter(find.text(CreationText.createActionAddContactShort))
          .dy,
      lessThan(
        tester.getCenter(find.text(ChatText.createActionCreateGroupShort)).dy,
      ),
    );
    expect(
      tester.getCenter(find.text(ChatText.createActionCreateGroupShort)).dy,
      lessThan(
        tester
            .getCenter(find.text(CreationText.createActionCreateCircleShort))
            .dy,
      ),
    );
    expect(
      tester
          .getCenter(find.text(CreationText.createActionCreateCircleShort))
          .dy,
      lessThan(
        tester
            .getCenter(
              find.text(CreationText.createActionInterestMatchShort),
            )
            .dy,
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

    await tester.tap(find.text(CreationText.createActionPostVideoShort));
    await tester.pump();

    expect(selected, EditorStartAction.video);
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
                    onContinueFromDraft: () {},
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        expect(
          find.text(CreationText.createActionPostPhotoShort),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionPhotoSubtitle),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionPostVideoShort),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionCameraSubtitle),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionWriteLong),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionAddContactShort),
          findsOneWidget,
        );
        expect(
          find.text(ChatText.createActionCreateGroupShort),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionCreateCircleShort),
          findsOneWidget,
        );
        expect(
          find.text(CreationText.createActionInterestMatchShort),
          findsOneWidget,
        );
        expect(find.text('发布'), findsNothing);
        expect(find.text('互动'), findsNothing);
        expect(find.text('发图片'), findsNothing);
        expect(find.text('发视频'), findsNothing);
        expect(find.text('写长文'), findsNothing);
        expect(find.text('续草稿'), findsNothing);
        expect(find.text('建圈子'), findsNothing);
        expect(
          find.descendant(
            of: find.byKey(TestKeys.modalBottomSheetPanel),
            matching: find.byType(Icon),
          ),
          findsNothing,
        );
        expect(find.byType(ConversationSheetListCard), findsNWidgets(2));

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

  testWidgets('趣信上下文优先级不改变移动端创作优先入口顺序', (tester) async {
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

    final galleryY = tester
        .getCenter(find.text(CreationText.createActionPostPhotoShort))
        .dy;
    final cameraY = tester
        .getCenter(find.text(CreationText.createActionPostVideoShort))
        .dy;
    expect(galleryY, lessThan(cameraY));
    expect(find.text(ChatText.createActionCreateGroupShort), findsOneWidget);
  });

  testWidgets('移动端加号面板渲染社交动作并触发回调', (tester) async {
    var createCircleTapped = false;
    var interestMatchTapped = false;

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
                onInterestMatch: () => interestMatchTapped = true,
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
      find.text(CreationText.createActionCreateCircleShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionAddContactShort),
      findsOneWidget,
    );
    expect(find.text(ChatText.createActionCreateGroupShort), findsOneWidget);
    expect(
      find.text(CreationText.createActionInterestMatchShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionInterestMatchSubtitle),
      findsOneWidget,
    );
    expect(find.byType(ConversationSheetListCard), findsNWidgets(2));
    expect(
      find.descendant(
        of: find.byKey(TestKeys.modalBottomSheetPanel),
        matching: find.byType(Icon),
      ),
      findsNothing,
    );

    await tester.tap(find.text(CreationText.createActionCreateCircleShort));
    await tester.pump();

    expect(createCircleTapped, isTrue);

    await tester.tap(find.text(CreationText.createActionInterestMatchShort));
    await tester.pump();

    expect(interestMatchTapped, isTrue);
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
