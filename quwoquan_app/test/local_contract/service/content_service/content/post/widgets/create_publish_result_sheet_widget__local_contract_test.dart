import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_publish_result_sheet.dart';

void main() {
  testWidgets('发布成功页提供查看作品和完成两个明确出口', (tester) async {
    CreatePublishResultAction? selectedAction;
    await tester.pumpWidget(
      _ResultSheetTestApp(
        onOpen: (context) async {
          selectedAction = await showCreatePublishResultSheet(
            context,
            state: CreatePublishResultState.published,
            postId: 'post-result-1',
          );
        },
      ),
    );

    await tester.tap(find.text('打开结果页'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createPublishResultSheet), findsOneWidget);
    expect(
      find.text(CreationText.publishResultSuccessTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsOneWidget,
    );

    await tester.tap(find.byKey(TestKeys.createPublishResultViewWorkButton));
    await tester.pumpAndSettle();
    expect(selectedAction, CreatePublishResultAction.viewWork);
  });

  testWidgets('媒体处理态只允许安全返回，不误报发布成功', (tester) async {
    await tester.pumpWidget(
      _ResultSheetTestApp(
        onOpen: (context) async {
          await showCreatePublishResultSheet(
            context,
            state: CreatePublishResultState.queued,
          );
        },
      ),
    );

    await tester.tap(find.text('打开结果页'));
    await tester.pumpAndSettle();

    expect(find.text(CreationText.publishResultQueuedTitle), findsOneWidget);
    expect(find.text(CreationText.publishResultSuccessTitle), findsNothing);
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsNothing,
    );
    expect(find.byKey(TestKeys.createPublishResultDoneButton), findsOneWidget);
  });

  testWidgets('后台发布受理后结果面原位更新真实状态和作品入口', (tester) async {
    final presentation = ValueNotifier<CreatePublishResultPresentation>(
      const CreatePublishResultPresentation(
        state: CreatePublishResultState.queued,
      ),
    );
    await tester.pumpWidget(
      _ResultSheetTestApp(
        onOpen: (context) async {
          await showCreatePublishResultSheet(
            context,
            state: CreatePublishResultState.queued,
            presentationListenable: presentation,
          );
        },
      ),
    );

    await tester.tap(find.text('打开结果页'));
    await tester.pumpAndSettle();
    expect(find.text(CreationText.publishResultQueuedTitle), findsOneWidget);

    presentation.value = const CreatePublishResultPresentation(
      state: CreatePublishResultState.pendingReview,
      postId: 'post-background-accepted',
    );
    await tester.pump();
    expect(
      find.text(CreationText.publishResultPendingReviewTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsNothing,
    );

    presentation.value = const CreatePublishResultPresentation(
      state: CreatePublishResultState.published,
      postId: 'post-background-accepted',
    );
    await tester.pump();
    expect(
      find.text(CreationText.publishResultSuccessTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsOneWidget,
    );

    await tester.tap(find.byKey(TestKeys.createPublishResultDoneButton));
    await tester.pumpAndSettle();
    presentation.dispose();
  });

  testWidgets('待审核回执明确显示审核状态且只能进入发布任务', (tester) async {
    CreatePublishResultAction? selectedAction;
    await tester.pumpWidget(
      _ResultSheetTestApp(
        onOpen: (context) async {
          selectedAction = await showCreatePublishResultSheet(
            context,
            state: CreatePublishResultState.pendingReview,
            postId: 'post-pending-review',
          );
        },
      ),
    );

    await tester.tap(find.text('打开结果页'));
    await tester.pumpAndSettle();

    expect(
      find.text(CreationText.publishResultPendingReviewTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(TestKeys.createPublishResultViewWorkButton),
      findsNothing,
    );
    expect(find.text(CreationText.publishResultViewTasks), findsOneWidget);

    await tester.tap(find.text(CreationText.publishResultViewTasks));
    await tester.pumpAndSettle();
    expect(selectedAction, CreatePublishResultAction.viewPublicationTasks);
  });
}

class _ResultSheetTestApp extends StatelessWidget {
  const _ResultSheetTestApp({required this.onOpen});

  final Future<void> Function(BuildContext context) onOpen;

  @override
  Widget build(BuildContext context) {
    return CupertinoApp(
      home: CupertinoPageScaffold(
        child: Builder(
          builder: (context) {
            return Center(
              child: CupertinoButton(
                onPressed: () async {
                  await onOpen(context);
                },
                child: const Text('打开结果页'),
              ),
            );
          },
        ),
      ),
    );
  }
}
