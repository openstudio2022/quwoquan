import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/pages/profile_comments_page.dart';

void main() {
  testWidgets('评论页加载失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _FailingCommentsRepository(),
          ),
        ],
        child: const MaterialApp(home: ProfileCommentsPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(UITextConstants.contentNotLoadedYet), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });
}

class _FailingCommentsRepository extends MockContentRepository {
  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('comments unavailable');
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('comments unavailable');
  }
}
