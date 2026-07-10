import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/career_interest_page.dart';

void main() {
  testWidgets('职业与兴趣页未保存返回使用 iOS alert 确认', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userProfileRepositoryProvider.overrideWithValue(
            const MockUserProfileRepository(),
          ),
          tagRepositoryProvider.overrideWithValue(MockTagRepository()),
        ],
        child: const MaterialApp(home: _CareerInterestHost()),
      ),
    );

    await tester.tap(find.text('打开职业与兴趣'));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.careerInterestTitle), findsOneWidget);
    await tester.tap(find.text('旅行').first);
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(
      find.text(UITextConstants.careerInterestUnsavedTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.careerInterestUnsavedMessage),
      findsOneWidget,
    );
    final dialog = find.byType(CupertinoAlertDialog);
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(UITextConstants.editProfileSaveAction),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(UITextConstants.careerInterestKeepEditing),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: dialog,
        matching: find.text(UITextConstants.careerInterestDiscard),
      ),
      findsOneWidget,
    );

    await tester.tap(
      find.descendant(
        of: dialog,
        matching: find.text(UITextConstants.careerInterestKeepEditing),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(CupertinoAlertDialog), findsNothing);
    expect(find.text(UITextConstants.careerInterestTitle), findsOneWidget);
  });

  testWidgets('销毁带摇摆标签的职业与兴趣页不会抛异常', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userProfileRepositoryProvider.overrideWithValue(
            const MockUserProfileRepository(),
          ),
          tagRepositoryProvider.overrideWithValue(MockTagRepository()),
        ],
        child: const MaterialApp(home: _CareerInterestHost()),
      ),
    );

    await tester.tap(find.text('打开职业与兴趣'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('旅行').first);
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text(UITextConstants.careerInterestDiscard));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text(UITextConstants.careerInterestTitle), findsNothing);
    expect(find.text('打开职业与兴趣'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _CareerInterestHost extends StatefulWidget {
  const _CareerInterestHost();

  @override
  State<_CareerInterestHost> createState() => _CareerInterestHostState();
}

class _CareerInterestHostState extends State<_CareerInterestHost> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.of(context).push<bool>(
              MaterialPageRoute<bool>(
                builder: (_) => const CareerInterestPage(),
              ),
            );
          },
          child: const Text('打开职业与兴趣'),
        ),
      ),
    );
  }
}
