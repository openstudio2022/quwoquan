import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';

void main() {
  testWidgets('关闭旧 flag 时仍保留统一三项创作入口', (tester) async {
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
                onContinueFromDraft: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.text(UITextConstants.createActionPostPhotoShort),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionPhotoSubtitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.createActionWriteLong), findsOneWidget);
    expect(find.text(UITextConstants.createActionResumeDraft), findsNothing);
    expect(
      find.text(UITextConstants.createActionCameraSubtitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionPostVideoShort),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionAddContactShort),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionCreateGroupShort),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.createActionCreateCircleShort),
      findsOneWidget,
    );
    expect(find.text('发点滴'), findsNothing);
  });
}
