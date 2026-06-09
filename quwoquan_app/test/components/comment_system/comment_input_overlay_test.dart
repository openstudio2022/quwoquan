import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/components/comment_system/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      ownerId: 'test-user',
      activeSubAccountId: 'test-sub-account',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

void main() {
  testWidgets('评论输入浮层不展示语音或 ASR 入口', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(MockContentRepository()),
          analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
        ],
        child: CupertinoApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: CupertinoPageScaffold(
            child: Builder(
              builder: (context) {
                return CupertinoButton(
                  onPressed: () =>
                      CommentInputOverlay.show(context, postId: 'post_001'),
                  child: const Text('open-comment-input'),
                );
              },
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsNothing);
    expect(find.byIcon(CupertinoIcons.mic), findsNothing);
    expect(find.text(UITextConstants.voiceInput), findsNothing);
  });

  testWidgets(
    'testCommentComposerMentionsAndAttachment: @、附件和 emoji 面板可协同提交',
    testCommentComposerMentionsAndAttachment,
  );
}

Future<void> testCommentComposerMentionsAndAttachment(
  WidgetTester tester,
) async {
  SharedPreferences.setMockInitialValues(const <String, Object>{});
  final submittedPayloads = <CommentComposerPayload>[];
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        contentRepositoryProvider.overrideWithValue(MockContentRepository()),
        analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        commentRemoteConfigProvider.overrideWithValue(
          const CommentRemoteConfig(maxImageAttachments: 1),
        ),
      ],
      child: CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CupertinoPageScaffold(
          child: Builder(
            builder: (context) {
              return CupertinoButton(
                onPressed: () => CommentInputOverlay.show(
                  context,
                  postId: 'comment-compose-post',
                  config: const CommentConfig(maxImageAttachments: 1),
                  mentionCandidates: const <CommentMentionCandidate>[
                    CommentMentionCandidate(
                      subjectType: 'assistant',
                      subjectId: 'assistant_xiaoqu',
                      displayName: UITextConstants.assistantEntryXiaoqu,
                    ),
                    CommentMentionCandidate(
                      subjectType: 'user',
                      subjectId: 'mutual_user_1',
                      displayName: '互相关注小雨',
                    ),
                    CommentMentionCandidate(
                      subjectType: 'user',
                      subjectId: 'following_user_1',
                      displayName: '关注阿青',
                    ),
                  ],
                  onSubmit: (payload) => submittedPayloads.add(payload),
                ),
                child: const Text('open-comment-input'),
              );
            },
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('open-comment-input'));
  await tester.pumpAndSettle();

  expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
  expect(find.byKey(TestKeys.commentTextField), findsOneWidget);

  await tester.enterText(
    find.byKey(TestKeys.commentTextField),
    '很喜欢这张图',
  );
  await tester.pump();

  await tester.tap(find.byKey(TestKeys.commentAtXiaoquButton));
  await tester.pump();

  final textField = tester.widget<CupertinoTextField>(
    find.byKey(TestKeys.commentTextField),
  );
  expect(
    textField.controller?.text,
    contains('@小趣'),
    reason: '点击 @ 应先插入默认小趣候选',
  );

  await tester.tap(find.byIcon(CupertinoIcons.photo).first);
  await tester.pumpAndSettle();

  await tester.tap(find.byIcon(CupertinoIcons.smiley));
  await tester.pumpAndSettle();
  expect(find.byType(UnifiedEmojiPicker), findsOneWidget);

  await tester.tap(find.byIcon(CupertinoIcons.keyboard));
  await tester.pumpAndSettle();

  await tester.tap(find.byKey(TestKeys.submitCommentButton));
  await tester.pumpAndSettle();

  expect(submittedPayloads, hasLength(1));
  final payload = submittedPayloads.single;
  expect(payload.content, contains('@小趣'));
  expect(payload.attachmentMediaIds, hasLength(1));
  expect(payload.mentions, hasLength(1));
  expect(
    payload.mentions.single.displayName,
    equals(UITextConstants.assistantEntryXiaoqu),
  );
}
