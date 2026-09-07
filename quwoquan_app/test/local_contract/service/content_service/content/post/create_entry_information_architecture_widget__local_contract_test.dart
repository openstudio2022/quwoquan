import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_entry_sheet.dart';

void main() {
  testWidgets('首层固定照片视频文字与更多，活动不直接暴露', (tester) async {
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
    expect(find.text(CreationText.createActionAddContactShort), findsNothing);
    expect(find.text(CreationText.createActionCreateCircleShort), findsNothing);
    // 「交集配对」launcher 已退役（intersection-unified-experience REQ-005），文案常量随之删除。
    expect(find.text('交集配对'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createActionCapture));
    await tester.pump();

    expect(selectedAction, EditorStartAction.video);
  });
}
