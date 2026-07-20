import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/comments/providers/comment_provider.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/recording_content_media_facet.dart';
import '../../../../support/cloud_services/test_content_comment_facet.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/runtime_failure_fixtures.dart';

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
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final tempDir = await Directory.systemTemp.createTemp(
      'comment_overlay_test_',
    );
    Hive.init(tempDir.path);
  });

  testWidgets('评论输入浮层不展示语音或 ASR 入口', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...mockContentFacetOverrides(MockContentRepository()),
          analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
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
                    postId: 'post_001',
                    sourceSurface: AppUiSurfaces.homeFeed,
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
    expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsNothing);
    expect(find.byIcon(CupertinoIcons.mic), findsNothing);
    expect(find.text(ChatText.voiceInput), findsNothing);
  });

  testWidgets(
    'testCommentComposerMentionsAndAttachment: @、附件和 emoji 面板可协同提交',
    testCommentComposerMentionsAndAttachment,
  );

  test(
    'testCommentSubmitThroughProvider: 已登录经 provider 真实提交评论并乐观入列',
    testCommentSubmitThroughProvider,
  );

  testWidgets('字数计数：输入后显示当前/上限，清空后隐藏', (tester) async {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    await tester.pumpWidget(_overlayHarness(postId: 'char-counter-post'));
    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.commentCharCounter), findsNothing);

    await tester.enterText(find.byKey(TestKeys.commentTextField), '你好世界');
    await tester.pump();
    expect(find.byKey(TestKeys.commentCharCounter), findsOneWidget);
    expect(find.text('4/500'), findsOneWidget);

    await tester.enterText(find.byKey(TestKeys.commentTextField), '');
    await tester.pump();
    expect(find.byKey(TestKeys.commentCharCounter), findsNothing);
  });

  testWidgets('草稿持久化：关闭未发的输入态后重开自动续写', (tester) async {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    await tester.pumpWidget(_overlayHarness(postId: 'draft-post'));

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(TestKeys.commentTextField), '未发完的草稿');
    await tester.pump(const Duration(milliseconds: 400));

    await tester.tap(find.byKey(TestKeys.commentInputOverlayScrim));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.commentInputOverlay), findsNothing);

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();
    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.commentTextField),
    );
    expect(field.controller?.text, '未发完的草稿', reason: '重开同帖输入态应续写草稿');
  });

  testWidgets('草稿清除：提交成功后重开不再回灌', (tester) async {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    final submitted = <CommentComposerPayload>[];
    await tester.pumpWidget(
      _overlayHarness(
        postId: 'draft-clear-post',
        onSubmit: (payload) => submitted.add(payload),
      ),
    );

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(TestKeys.commentTextField), '这条会发出去');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.byKey(TestKeys.submitCommentButton));
    await tester.pumpAndSettle();
    expect(submitted, hasLength(1));

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();
    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.commentTextField),
    );
    expect(field.controller?.text, isEmpty, reason: '提交成功后草稿应已清除');
  });

  testWidgets('评论频控失败展示结构化恢复反馈并保留可编辑草稿', (tester) async {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    await tester.pumpWidget(
      _overlayHarness(
        postId: 'rate-limited-post',
        onSubmit: (_) => throw CloudException(
          type: CloudErrorType.rateLimited,
          message: 'comment rate limited',
          statusCode: 429,
          code: 'CONTENT.USER.comment_rate_limited',
          userMessage: '操作太频繁，请稍后再试',
          runtimeFailure: testRuntimeFailure(
            code: 'CONTENT.USER.comment_rate_limited',
            kind: RuntimeFailureKind.rateLimited,
            nature: RuntimeFailureNature.transient,
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-comment-input'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(TestKeys.commentTextField), '频控后仍需保留');
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.submitCommentButton));
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(find.text('操作太频繁，请稍后再试'), findsOneWidget);
    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.commentTextField),
    );
    expect(field.enabled, isTrue);
    expect(field.controller?.text, '频控后仍需保留');
  });
}

Widget _overlayHarness({
  required String postId,
  FutureOr<void> Function(CommentComposerPayload payload)? onSubmit,
}) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(MockContentRepository()),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      activePersonaContextProvider.overrideWith(
        (ref) async => const ActivePersonaContextViewData(
          subAccountId: 'test-sub-account',
          ownerUserId: 'test-user',
          subjectType: 'subAccount',
          displayName: '测试用户',
          avatarUrl: '',
          personaContextVersion: '1',
        ),
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
                postId: postId,
                sourceSurface: AppUiSurfaces.homeFeed,
                onSubmit: onSubmit,
              ),
              child: const Text('open-comment-input'),
            );
          },
        ),
      ),
    ),
  );
}

/// 复现用户主路径：经 commentProvider.addComment（非自定义 onSubmit）提交评论。
/// 提交必须经 typed command，然后从权威查询投影回读，不构造兼容 DTO。
Future<void> testCommentSubmitThroughProvider() async {
  SharedPreferences.setMockInitialValues(const <String, Object>{});
  final repo = MockContentRepository();
  final comments = TestContentCommentFacet();
  const postId = 'alpha_photo_landscape_single';
  final container = ProviderContainer(
    overrides: [
      ...mockContentFacetOverrides(repo, commentFacet: comments),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      activePersonaContextProvider.overrideWith(
        (ref) async => const ActivePersonaContextViewData(
          subAccountId: 'test-sub-account',
          ownerUserId: 'test-user',
          subjectType: 'subAccount',
          displayName: '测试用户',
          avatarUrl: '',
          personaContextVersion: '1',
        ),
      ),
    ],
  );
  addTearDown(container.dispose);

  final notifier = container.read(commentProviderFamily(postId).notifier);
  final result = await notifier.addComment('测试发评论是否可用');

  expect(result, isNotNull, reason: 'addComment 应返回云侧确认评论');
  expect(comments.createCalls, 1, reason: '应真实调用一次 typed createComment');
  expect(comments.lastCreateCommand?.postId, postId);
  expect(comments.lastCreateCommand?.content, '测试发评论是否可用');
  final state = container.read(commentProviderFamily(postId));
  expect(
    state.comments.any((c) => c.content == '测试发评论是否可用'),
    isTrue,
    reason: '权威投影回读后评论应出现在列表中',
  );
}

Future<void> testCommentComposerMentionsAndAttachment(
  WidgetTester tester,
) async {
  SharedPreferences.setMockInitialValues(const <String, Object>{});
  final submittedPayloads = <CommentComposerPayload>[];
  final media = RecordingContentMediaFacet();
  const selectedPath = '/tmp/comment-attachment.jpg';
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...mockContentFacetOverrides(MockContentRepository()),
        analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        imagePickGatewayProvider.overrideWithValue(
          const _SelectedImagePickGateway(selectedPath),
        ),
        fileStorageGatewayProvider.overrideWithValue(
          const _MemoryFileStorageGateway(<String, List<int>>{
            selectedPath: <int>[1, 2, 3, 4],
          }),
        ),
        contentMediaSourceReaderProvider.overrideWithValue(
          const _MemoryContentMediaSourceReader(<String, List<int>>{
            selectedPath: <int>[1, 2, 3, 4],
          }),
        ),
        homeFeedContentMediaFacetProvider.overrideWithValue(media),
        contentMediaStreamObjectUploadProvider.overrideWithValue(
          (
            _,
            _, {
            required contentLength,
            required contentType,
            required expectedSha256,
            abortTrigger,
          }) async {},
        ),
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
                  sourceSurface: AppUiSurfaces.homeFeed,
                  config: const CommentConfig(maxImageAttachments: 1),
                  mentionCandidates: <ContentCommentMention>[
                    ContentCommentMention(
                      subjectType: 'assistant',
                      subjectId: 'assistant_xiaoqu',
                      displayName: AssistantText.assistantEntryXiaoqu,
                    ),
                    ContentCommentMention(
                      subjectType: 'user',
                      subjectId: 'mutual_user_1',
                      displayName: '互相关注小雨',
                    ),
                    ContentCommentMention(
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

  await tester.enterText(find.byKey(TestKeys.commentTextField), '很喜欢这张图');
  await tester.pump();

  await tester.tap(find.byKey(TestKeys.commentMentionButton));
  await tester.pumpAndSettle();
  expect(
    find.text(AssistantText.assistantEntryXiaoqu),
    findsOneWidget,
    reason: '点击 @ 后应展示可选择的小趣候选',
  );
  await tester.tap(find.text(AssistantText.assistantEntryXiaoqu));
  await tester.pump();

  final textField = tester.widget<CupertinoTextField>(
    find.byKey(TestKeys.commentTextField),
  );
  expect(
    textField.controller?.text,
    contains('@小趣'),
    reason: '选择小趣候选后应插入可见的 @小趣 文本',
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
  expect(media.initCommands, hasLength(1));
  expect(media.completedSessions, <String>['session_1']);
  expect(media.abortedSessions, isEmpty);
  expect(payload.attachmentMediaIds.single, 'image_asset_1');
  expect(payload.mentions, hasLength(1));
  expect(
    payload.mentions.single.displayName,
    equals(AssistantText.assistantEntryXiaoqu),
  );
}

final class _SelectedImagePickGateway implements ImagePickGateway {
  const _SelectedImagePickGateway(this.path);

  final String path;

  @override
  Future<String?> pickImage(
    BuildContext context, {
    required ImagePickSource source,
    required String cameraRouteName,
    required String galleryRouteName,
  }) async => path;
}

final class _MemoryFileStorageGateway implements FileStorageGateway {
  const _MemoryFileStorageGateway(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async => '/tmp/support';

  @override
  Future<String> temporaryPath() async => '/tmp';

  @override
  Future<bool> exists(String path) async => bytesByPath.containsKey(path);

  @override
  Future<String> readAsString(String path) async => '';

  @override
  Future<void> writeAsString(String path, String contents) async {}

  @override
  Future<List<int>> readAsBytes(String path) async => bytesByPath[path]!;

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];
}

final class _MemoryContentMediaSourceReader
    implements ContentMediaSourceReader {
  const _MemoryContentMediaSourceReader(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  Future<PreparedContentMediaSource> prepare(String localPath) {
    final bytes = bytesByPath[localPath];
    if (bytes == null) {
      throw StateError('missing in-memory media source: $localPath');
    }
    return prepareContentMediaSource(
      fileSize: bytes.length,
      openRead: () => Stream<List<int>>.value(bytes),
    );
  }
}
