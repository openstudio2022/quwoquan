import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
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

    expect(find.text('从相册选择'), findsOneWidget);
    expect(find.text('写文字'), findsOneWidget);
    expect(find.text('相机'), findsOneWidget);
    expect(find.text('发起群聊'), findsOneWidget);
    expect(find.text('添加同好'), findsOneWidget);
    expect(find.text('作品'), findsNothing);
    expect(find.text('文章'), findsNothing);

    await tester.tap(find.text('相机'));
    await tester.pump();

    expect(selected, EditorStartAction.capture);
  });
}
