import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_entry_sheet.dart';

void main() {
  testWidgets('关闭旧 flag 时仍保留统一三项首层入口', (tester) async {
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

    await tester.tap(find.byKey(TestKeys.createActionPublishContent));
    await tester.pump();

    expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
    expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);
    expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
  });
}
