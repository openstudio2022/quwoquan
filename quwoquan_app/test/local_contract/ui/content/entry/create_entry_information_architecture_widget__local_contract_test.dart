import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  testWidgets('首层入口保留三种创作动作与社交动作，不再暴露旧六宫格 taxonomy', (tester) async {
    EditorStartAction? selectedAction;

    await tester.pumpWidget(
      ProviderScope(
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (context, _) => MaterialApp(
            home: Scaffold(
              body: CreateEntrySheet(
                isOpen: true,
                onClose: () {},
                onSelect: (action) => selectedAction = action,
                onContinueFromDraft: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
    expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
    expect(find.byKey(TestKeys.createActionContinueFromDraft), findsNothing);
    expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);

    expect(find.text('发布'), findsNothing);
    expect(find.text('互动'), findsNothing);
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
    expect(find.text(CreationText.createActionWriteLong), findsOneWidget);
    expect(
      find.text(CreationText.createActionCameraSubtitle),
      findsOneWidget,
    );
    expect(find.text(CreationText.createActionResumeDraft), findsNothing);
    expect(
      find.text(CreationText.createActionAddContactShort),
      findsOneWidget,
    );
    expect(find.text(ChatText.createActionCreateGroupShort), findsOneWidget);
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
    expect(find.text('创作'), findsNothing);
    expect(find.text('连接'), findsNothing);
    expect(find.text('取消'), findsOneWidget);

    expect(find.text('发微趣'), findsNothing);
    expect(find.text('发美图'), findsNothing);
    expect(find.text('写文章'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createActionCapture));
    await tester.pump();

    expect(selectedAction, EditorStartAction.video);
  });
}
