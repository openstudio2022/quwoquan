import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  testWidgets('创作首层入口仅暴露三种开始动作，不再暴露旧六宫格 taxonomy', (tester) async {
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
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
    expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
    expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);

    expect(find.text('从相册选'), findsOneWidget);
    expect(find.text('写点什么'), findsOneWidget);
    expect(find.text('拍一下'), findsOneWidget);

    expect(find.text('发微趣'), findsNothing);
    expect(find.text('发美图'), findsNothing);
    expect(find.text('发视频'), findsNothing);
    expect(find.text('写文章'), findsNothing);

    await tester.tap(find.byKey(TestKeys.createActionCapture));
    await tester.pump();

    expect(selectedAction, EditorStartAction.capture);
  });
}
