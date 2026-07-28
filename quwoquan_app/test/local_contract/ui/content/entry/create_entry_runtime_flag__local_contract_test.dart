import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
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
      find.text(CreationText.createActionPostPhotoShort),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionPhotoSubtitle),
      findsOneWidget,
    );
    expect(find.text(CreationText.createActionWriteLong), findsOneWidget);
    expect(find.text(CreationText.createActionResumeDraft), findsNothing);
    expect(
      find.text(CreationText.createActionCameraSubtitle),
      findsOneWidget,
    );
    expect(
      find.text(CreationText.createActionPostVideoShort),
      findsOneWidget,
    );
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
    expect(find.text('发点滴'), findsNothing);
  });
}
