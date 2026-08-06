import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_entry_sheet.dart';

void main() {
  testWidgets('首层固定发内容活动群聊，发内容后二级固定照片视频文字', (tester) async {
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
                onStartGathering: () {},
                onStartGroupChat: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(TestKeys.createActionPublishContent), findsOneWidget);
    expect(find.byKey(TestKeys.createActionStartGathering), findsOneWidget);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsOneWidget);
    expect(find.byKey(TestKeys.createActionGallery), findsNothing);
    expect(find.byKey(TestKeys.createActionCapture), findsNothing);
    expect(find.byKey(TestKeys.createActionWrite), findsNothing);
    expect(find.text(CreationText.createActionAddContactShort), findsNothing);
    expect(find.text(CreationText.createActionCreateCircleShort), findsNothing);
    expect(
      find.text(CreationText.createActionInterestMatchShort),
      findsNothing,
    );

    await tester.tap(find.byKey(TestKeys.createActionPublishContent));
    await tester.pump();

    expect(find.byKey(TestKeys.createActionPublishContent), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGathering), findsNothing);
    expect(find.byKey(TestKeys.createActionStartGroupChat), findsNothing);
    expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
    expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);
    expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.createActionCapture));
    await tester.pump();

    expect(selectedAction, EditorStartAction.video);
  });
}
