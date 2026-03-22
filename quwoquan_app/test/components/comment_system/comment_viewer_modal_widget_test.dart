import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  testWidgets('评论面板以非全屏底部面板呈现', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => CupertinoButton(
                onPressed: () => CommentViewer.showModal(
                  context: context,
                  postId: 'mock-post-id',
                ),
                child: const Text('open-comments'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-comments'));
    await tester.pumpAndSettle();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    expect(panel, findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(0));
  });
}
