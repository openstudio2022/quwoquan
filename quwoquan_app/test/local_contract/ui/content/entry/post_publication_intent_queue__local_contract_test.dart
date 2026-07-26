import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../support/runtime_failure_fixtures.dart';
import '../../../../support/recording_content_media_facet.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('发布意图先持久化，进程重启后自动重放并删除已发布草稿', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final failingWriter = _FailingPublicationWriter();
    final firstDrafts = _RecordingDraftRepository();
    final first = _container(writer: failingWriter, drafts: firstDrafts);
    addTearDown(first.dispose);

    final notifier = first.read(postPublicationIntentQueueProvider.notifier);
    await expectLater(
      notifier.submit(
        command: _command(),
        authorPersonaId: 'persona-publication',
      ),
      throwsA(isA<PostPublicationQueuedException>()),
    );
    expect(
      first.read(postPublicationIntentQueueProvider).intents,
      hasLength(1),
    );
    final persisted = (await SharedPreferences.getInstance()).getString(
      'post_publication_intents_v1:user-publication',
    );
    expect(persisted, isNotNull);
    first.dispose();

    final successfulWriter = _SuccessfulPublicationWriter();
    final recoveredDrafts = _RecordingDraftRepository();
    final recovered = _container(
      writer: successfulWriter,
      drafts: recoveredDrafts,
    );
    addTearDown(recovered.dispose);
    recovered.read(postPublicationIntentQueueProvider);
    await _waitForHydration(recovered);
    await recovered
        .read(postPublicationIntentQueueProvider.notifier)
        .flushNow();
    await _waitForPublication(successfulWriter);

    expect(successfulWriter.commands, hasLength(1));
    expect(successfulWriter.commands.single.publishIntentId, 'intent-1');
    expect(recoveredDrafts.deletedDraftIds, <String>['draft-1']);
    expect(recovered.read(postPublicationIntentQueueProvider).intents, isEmpty);
  });

  test('同一本地草稿重复提交始终复用首次不可变意图', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final writer = _FailingPublicationWriter();
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );

    await expectLater(
      notifier.submit(
        command: _command(),
        authorPersonaId: 'persona-publication',
      ),
      throwsA(isA<PostPublicationQueuedException>()),
    );
    await expectLater(
      notifier.submit(
        command: SubmitContentPostPublicationCommand(
          publishIntentId: 'intent-should-be-ignored',
          localDraftId: 'draft-1',
          contentType: ContentPostType.micro,
          body: 'changed after first click',
        ),
        authorPersonaId: 'persona-publication',
      ),
      throwsA(isA<PostPublicationQueuedException>()),
    );

    expect(writer.commands, hasLength(2));
    expect(
      writer.commands.map((command) => command.publishIntentId).toSet(),
      <String>{'intent-1'},
    );
  });

  test('媒体准备首击先持久化，后台队列不会提交未上传素材', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final writer = _SuccessfulPublicationWriter();
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );

    await notifier.beginMediaPreparation(
      command: _command(contentType: ContentPostType.image),
      authorPersonaId: 'persona-publication',
    );
    await notifier.flushNow();

    final intent = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(intent.requiresMediaPreparation, isTrue);
    expect(intent.command.mediaAssetIds, isEmpty);
    expect(writer.commands, isEmpty);

    await notifier.retryPending('draft-1');
    expect(writer.commands, isEmpty);
    expect(
      (await SharedPreferences.getInstance()).getString(
        'post_publication_intents_v1:user-publication',
      ),
      contains('"stage":"preparingMedia"'),
    );
  });

  test('媒体准备检查点重启后保留资产身份和源摘要', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final first = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: _RecordingDraftRepository(),
    );
    final notifier = first.read(postPublicationIntentQueueProvider.notifier);
    await notifier.beginMediaPreparation(
      command: _command(contentType: ContentPostType.video),
      authorPersonaId: 'persona-publication',
    );
    await notifier.recordPreparedMediaAsset(
      'draft-1',
      ContentMediaPreparationCheckpoint.forSource(
        preparationIdentity: 'draft-1',
        slot: 'video:0',
        mediaType: ContentMediaType.video,
        sha256Digest: 'sha256:video-source-digest',
      ).copyWith(
        sessionId: 'session-video-1',
        assetId: 'video_asset_1',
        phase: ContentMediaPreparationPhase.completed,
      ),
    );
    first.dispose();

    final recovered = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: _RecordingDraftRepository(),
    );
    addTearDown(recovered.dispose);
    recovered.read(postPublicationIntentQueueProvider);
    await _waitForHydration(recovered);

    final checkpoint = recovered
        .read(postPublicationIntentQueueProvider)
        .intents
        .single
        .preparedMediaAssets
        .single;
    expect(checkpoint.slot, 'video:0');
    expect(checkpoint.mediaType, ContentMediaType.video);
    expect(checkpoint.sha256Digest, 'sha256:video-source-digest');
    expect(checkpoint.assetId, 'video_asset_1');
    expect(checkpoint.sessionId, 'session-video-1');
    expect(checkpoint.phase, ContentMediaPreparationPhase.completed);
    expect(checkpoint.initIdempotencyKey, isNotEmpty);
    expect(checkpoint.completeIdempotencyKey, isNotEmpty);
    expect(checkpoint.abortIdempotencyKey, isNotEmpty);
    expect(checkpoint.discardIdempotencyKey, isNotEmpty);
  });

  test('放弃媒体准备前先与服务端会话对账并中止 pending session', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final media = RecordingContentMediaFacet();
    final container = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: _RecordingDraftRepository(),
      media: media,
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    await notifier.beginMediaPreparation(
      command: _command(contentType: ContentPostType.video),
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = ContentMediaPreparationCheckpoint.forSource(
      preparationIdentity: 'draft-1',
      slot: 'video:0',
      mediaType: ContentMediaType.video,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: ContentMediaType.video,
        contentType: 'video/mp4',
        fileSize: 4,
        expectedSha256: 'sha256:$_pendingVideoDigest',
      ),
      ContentMediaUploadCommandContext(
        idempotencyKey: checkpoint.initIdempotencyKey,
      ),
    );
    await notifier.recordPreparedMediaAsset(
      'draft-1',
      checkpoint.copyWith(
        sessionId: initialized.sessionId,
        phase: ContentMediaPreparationPhase.uploading,
      ),
    );

    await notifier.cancelPending('draft-1');

    expect(media.abortedSessions, <String>[initialized.sessionId]);
    expect(container.read(postPublicationIntentQueueProvider).intents, isEmpty);
  });

  test('放弃已完成媒体时先取得 discarded 回执再移除本地意图', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final media = RecordingContentMediaFacet();
    final container = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: _RecordingDraftRepository(),
      media: media,
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    await notifier.beginMediaPreparation(
      command: _command(contentType: ContentPostType.image),
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = ContentMediaPreparationCheckpoint.forSource(
      preparationIdentity: 'draft-1',
      slot: 'image:0',
      mediaType: ContentMediaType.image,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: ContentMediaType.image,
        contentType: 'image/jpeg',
        fileSize: 4,
        expectedSha256: 'sha256:$_pendingVideoDigest',
      ),
      ContentMediaUploadCommandContext(
        idempotencyKey: checkpoint.initIdempotencyKey,
      ),
    );
    final completed = await media.completeUpload(
      CompleteContentMediaUploadCommand(sessionId: initialized.sessionId),
      ContentMediaUploadCommandContext(
        idempotencyKey: checkpoint.completeIdempotencyKey,
      ),
    );
    final completedAssetId = completed.assetId!;
    final completedCheckpoint = checkpoint.copyWith(
      sessionId: initialized.sessionId,
      assetId: completedAssetId,
      phase: ContentMediaPreparationPhase.completed,
    );
    await notifier.recordPreparedMediaAsset('draft-1', completedCheckpoint);

    await notifier.cancelPending('draft-1');

    expect(media.discardCommands.map((command) => command.mediaId), <String>[
      completedAssetId,
    ]);
    expect(media.discardIdempotencyKeys, <String>[
      completedCheckpoint.discardIdempotencyKey,
    ]);
    expect(container.read(postPublicationIntentQueueProvider).intents, isEmpty);
  });

  test('提交失败后的未受理意图仍会回收已完成媒体', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final media = RecordingContentMediaFacet();
    final writer = _CloudFailingPublicationWriter(
      CloudException(
        type: CloudErrorType.server,
        message: 'temporary publication failure',
        runtimeFailure: testRuntimeFailure(
          code: 'CONTENT.SYSTEM.storage_write_failed',
          nature: RuntimeFailureNature.transient,
          recovery: const RuntimeRecoveryDirective(
            action: 'retry',
            afterSeconds: 1,
            disruptionLevel: 'silent',
          ),
        ),
      ),
    );
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
      media: media,
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    final command = _command(contentType: ContentPostType.image);
    await notifier.beginMediaPreparation(
      command: command,
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = ContentMediaPreparationCheckpoint.forSource(
      preparationIdentity: 'draft-1',
      slot: 'image:0',
      mediaType: ContentMediaType.image,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: ContentMediaType.image,
        contentType: 'image/jpeg',
        fileSize: 4,
        expectedSha256: 'sha256:$_pendingVideoDigest',
      ),
      ContentMediaUploadCommandContext(
        idempotencyKey: checkpoint.initIdempotencyKey,
      ),
    );
    final completed = await media.completeUpload(
      CompleteContentMediaUploadCommand(sessionId: initialized.sessionId),
      ContentMediaUploadCommandContext(
        idempotencyKey: checkpoint.completeIdempotencyKey,
      ),
    );
    final completedAssetId = completed.assetId!;
    await notifier.recordPreparedMediaAsset(
      'draft-1',
      checkpoint.copyWith(
        sessionId: initialized.sessionId,
        assetId: completedAssetId,
        phase: ContentMediaPreparationPhase.completed,
      ),
    );
    await expectLater(
      notifier.submit(command: command, authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationQueuedException>()),
    );

    await notifier.cancelPending('draft-1');

    expect(media.discardCommands, hasLength(1));
    expect(media.discardCommands.single.mediaId, completedAssetId);
    expect(container.read(postPublicationIntentQueueProvider).intents, isEmpty);
  });

  test('媒体处理中按 metadata recovery=retry 入队而不是永久阻断', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final writer = _CloudFailingPublicationWriter(
      CloudException(
        type: CloudErrorType.invalidResponse,
        message: 'media is processing',
        code: 'CONTENT.USER.media_not_ready',
        runtimeFailure: testRuntimeFailure(
          code: 'CONTENT.USER.media_not_ready',
          nature: RuntimeFailureNature.transient,
          recovery: const RuntimeRecoveryDirective(
            action: 'retry',
            afterSeconds: 2,
            disruptionLevel: 'silent',
          ),
        ),
      ),
    );
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
    );
    addTearDown(container.dispose);

    await expectLater(
      container
          .read(postPublicationIntentQueueProvider.notifier)
          .submit(command: _command(), authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationQueuedException>()),
    );

    final intent = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(intent.blocked, isFalse);
    expect(intent.lastErrorCode, 'CONTENT.USER.media_not_ready');
  });

  test('上传完成的 processing asset 在提交前入队，不依赖发布失败探测', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final media = RecordingContentMediaFacet(
      completedAssetStatus: ContentMediaProcessingStatus.processing,
    );
    final writer = _SuccessfulPublicationWriter();
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
      media: media,
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    final command = _command(contentType: ContentPostType.image);
    await _recordCompletedMedia(
      notifier: notifier,
      media: media,
      command: command,
    );

    await expectLater(
      notifier.submit(command: command, authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationQueuedException>()),
    );

    final intent = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(writer.commands, isEmpty);
    expect(intent.blocked, isFalse);
    expect(intent.lastErrorCode, ContentErrorCode.mediaNotReady.code);
  });

  test('上传完成的 rejected asset 阻断发布并保留草稿', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final media = RecordingContentMediaFacet(
      completedAssetStatus: ContentMediaProcessingStatus.rejected,
    );
    final writer = _SuccessfulPublicationWriter();
    final drafts = _RecordingDraftRepository();
    final container = _container(writer: writer, drafts: drafts, media: media);
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    final command = _command(contentType: ContentPostType.image);
    await _recordCompletedMedia(
      notifier: notifier,
      media: media,
      command: command,
    );

    await expectLater(
      notifier.submit(command: command, authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationTaskBlockedException>()),
    );

    final intent = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(writer.commands, isEmpty);
    expect(intent.blocked, isTrue);
    expect(intent.lastErrorCode, ContentErrorCode.mediaProcessingRejected.code);
    expect(drafts.deletedDraftIds, isEmpty);
  });

  test('未授权即使 HTTP 分类曾可重试也按 reauthenticate 永久阻断', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final writer = _CloudFailingPublicationWriter(
      CloudException(
        type: CloudErrorType.unauthorized,
        message: 'session expired',
        code: 'USER.AUTH.session_expired',
        runtimeFailure: testRuntimeFailure(
          code: 'USER.AUTH.session_expired',
          kind: RuntimeFailureKind.auth,
          recovery: const RuntimeRecoveryDirective(
            action: 'reauthenticate',
            disruptionLevel: 'blocking',
          ),
        ),
      ),
    );
    final container = _container(
      writer: writer,
      drafts: _RecordingDraftRepository(),
    );
    addTearDown(container.dispose);

    await expectLater(
      container
          .read(postPublicationIntentQueueProvider.notifier)
          .submit(command: _command(), authorPersonaId: 'persona-publication'),
      throwsA(isA<CloudException>()),
    );

    final intent = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(intent.blocked, isTrue);
    expect(intent.lastErrorCode, 'USER.AUTH.session_expired');
    expect(writer.commands, hasLength(1));
  });

  test('待审核回执保留草稿且只轮询状态，审核通过后才清理草稿', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final writer = _PendingReviewPublicationWriter();
    final drafts = _RecordingDraftRepository();
    final statusReader = _SequencePublicationStatusReader(
      <ContentPostPublicationState>[ContentPostPublicationState.published],
    );
    final container = _container(
      writer: writer,
      drafts: drafts,
      statusReader: statusReader,
    );
    addTearDown(container.dispose);

    final receipt = await container
        .read(postPublicationIntentQueueProvider.notifier)
        .submit(command: _command(), authorPersonaId: 'persona-publication');

    expect(receipt.state, 'pending_review');
    expect(drafts.deletedDraftIds, isEmpty);
    final pending = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(pending.publicationState, ContentPostPublicationState.pendingReview);
    expect(statusReader.requestedPostIds, isEmpty);

    await container
        .read(postPublicationIntentQueueProvider.notifier)
        .retryPending('draft-1');

    expect(statusReader.requestedPostIds, <String>['post-draft-1']);
    expect(drafts.deletedDraftIds, <String>['draft-1']);
    expect(container.read(postPublicationIntentQueueProvider).intents, isEmpty);
    expect(writer.commands, hasLength(1));
  });

  test('待审核内容被拒绝后保留草稿并形成可放弃的终态任务', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final drafts = _RecordingDraftRepository();
    final container = _container(
      writer: _PendingReviewPublicationWriter(),
      drafts: drafts,
      statusReader: _SequencePublicationStatusReader(
        <ContentPostPublicationState>[ContentPostPublicationState.rejected],
      ),
    );
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );

    await notifier.submit(
      command: _command(),
      authorPersonaId: 'persona-publication',
    );
    await notifier.retryPending('draft-1');

    final rejected = container
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(rejected.publicationState, ContentPostPublicationState.rejected);
    expect(rejected.blocked, isTrue);
    expect(drafts.deletedDraftIds, isEmpty);

    await notifier.cancelPending('draft-1');
    expect(container.read(postPublicationIntentQueueProvider).intents, isEmpty);
    expect(drafts.deletedDraftIds, isEmpty);
  });

  test('旧队列缺失阶段时安全恢复提交态并去重圈子投放目标', () {
    final now = DateTime.utc(2026, 7, 20);
    final stored =
        LocalPostPublicationIntent(
            command: _command(),
            authorPersonaId: 'persona-publication',
            circleIds: const <String>[],
            createdAt: now,
            nextAttemptAt: now,
          ).toStorageMap()
          ..remove('stage')
          ..['circleIds'] = <String>[' circle-a ', 'circle-a', '', 'circle-b'];

    final restored = LocalPostPublicationIntent.fromStorageMap(stored);

    expect(restored.stage, LocalPostPublicationStage.submitting);
    expect(restored.circleIds, <String>['circle-a', 'circle-b']);
  });
}

const String _pendingVideoDigest =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

ProviderContainer _container({
  required ContentPostPublicationWriter writer,
  required CreateDraftRepository drafts,
  ContentPostPublicationStatusReader? statusReader,
  ContentMediaFacet? media,
}) {
  return ProviderContainer(
    overrides: [
      currentUserIdProvider.overrideWithValue('user-publication'),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          subAccountId: 'persona-publication',
          ownerUserId: 'user-publication',
          displayName: '发布者',
          avatarUrl: '',
        ),
      ),
      createContentPostPublicationWriterProvider.overrideWithValue(writer),
      createWorkspaceContentPostPublicationStatusReaderProvider
          .overrideWithValue(
            statusReader ??
                _SequencePublicationStatusReader(
                  const <ContentPostPublicationState>[],
                ),
          ),
      createDraftRepositoryProvider.overrideWithValue(drafts),
      if (media != null)
        createContentMediaFacetProvider.overrideWithValue(media),
    ],
  );
}

Future<void> _waitForHydration(ProviderContainer container) async {
  for (var attempt = 0; attempt < 100; attempt++) {
    if (container.read(postPublicationIntentQueueProvider).hydrated) {
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('publication queue did not hydrate');
}

Future<void> _waitForPublication(_SuccessfulPublicationWriter writer) async {
  for (var attempt = 0; attempt < 300; attempt++) {
    if (writer.commands.isNotEmpty) {
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('publication queue did not replay');
}

Future<void> _recordCompletedMedia({
  required PostPublicationIntentQueueNotifier notifier,
  required RecordingContentMediaFacet media,
  required SubmitContentPostPublicationCommand command,
}) async {
  await notifier.beginMediaPreparation(
    command: command,
    authorPersonaId: 'persona-publication',
  );
  final checkpoint = ContentMediaPreparationCheckpoint.forSource(
    preparationIdentity: command.localDraftId,
    slot: 'image:0',
    mediaType: ContentMediaType.image,
    sha256Digest: 'sha256:$_pendingVideoDigest',
  );
  final initialized = await media.initUpload(
    InitContentMediaUploadCommand(
      mediaType: ContentMediaType.image,
      contentType: 'image/jpeg',
      fileSize: 4,
      expectedSha256: 'sha256:$_pendingVideoDigest',
    ),
    ContentMediaUploadCommandContext(
      idempotencyKey: checkpoint.initIdempotencyKey,
    ),
  );
  final completed = await media.completeUpload(
    CompleteContentMediaUploadCommand(sessionId: initialized.sessionId),
    ContentMediaUploadCommandContext(
      idempotencyKey: checkpoint.completeIdempotencyKey,
    ),
  );
  await notifier.recordPreparedMediaAsset(
    command.localDraftId,
    checkpoint.copyWith(
      sessionId: initialized.sessionId,
      assetId: completed.assetId!,
      phase: ContentMediaPreparationPhase.completed,
    ),
  );
}

SubmitContentPostPublicationCommand _command({
  ContentPostType contentType = ContentPostType.micro,
}) {
  return SubmitContentPostPublicationCommand(
    publishIntentId: 'intent-1',
    localDraftId: 'draft-1',
    contentType: contentType,
    body: 'publish once',
  );
}

final class _FailingPublicationWriter implements ContentPostPublicationWriter {
  final List<SubmitContentPostPublicationCommand> commands =
      <SubmitContentPostPublicationCommand>[];

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    throw StateError('offline');
  }
}

final class _SuccessfulPublicationWriter
    implements ContentPostPublicationWriter {
  final List<SubmitContentPostPublicationCommand> commands =
      <SubmitContentPostPublicationCommand>[];

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    return ContentPostPublicationReceipt(
      publishIntentId: command.publishIntentId,
      localDraftId: command.localDraftId,
      postId: 'post-${command.localDraftId}',
      state: 'published',
      committedVersion: 1,
      acceptedAt: DateTime.utc(2026, 7, 17),
    );
  }
}

final class _PendingReviewPublicationWriter
    implements ContentPostPublicationWriter {
  final List<SubmitContentPostPublicationCommand> commands =
      <SubmitContentPostPublicationCommand>[];

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    return ContentPostPublicationReceipt(
      publishIntentId: command.publishIntentId,
      localDraftId: command.localDraftId,
      postId: 'post-${command.localDraftId}',
      state: 'pending_review',
      committedVersion: 1,
      acceptedAt: DateTime.utc(2026, 7, 20),
    );
  }
}

final class _SequencePublicationStatusReader
    implements ContentPostPublicationStatusReader {
  _SequencePublicationStatusReader(this.states);

  final List<ContentPostPublicationState> states;
  final List<String> requestedPostIds = <String>[];

  @override
  Future<ContentPostPublicationStatus> getPostPublicationStatus(
    String postId,
  ) async {
    requestedPostIds.add(postId);
    if (states.isEmpty) {
      throw StateError('no publication status prepared');
    }
    final state = states.removeAt(0);
    return ContentPostPublicationStatus(
      postId: postId,
      state: state,
      moderationStatus: switch (state) {
        ContentPostPublicationState.pendingReview => 'pending',
        ContentPostPublicationState.published => 'approved',
        ContentPostPublicationState.rejected => 'rejected',
      },
      updatedAt: DateTime.utc(2026, 7, 20),
    );
  }
}

final class _CloudFailingPublicationWriter
    implements ContentPostPublicationWriter {
  _CloudFailingPublicationWriter(this.error);

  final CloudException error;
  final List<SubmitContentPostPublicationCommand> commands =
      <SubmitContentPostPublicationCommand>[];

  @override
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    throw error;
  }
}

final class _RecordingDraftRepository implements CreateDraftRepository {
  final List<String> deletedDraftIds = <String>[];

  @override
  Future<CreateDraftStoreState> deleteDraft(String draftId) async {
    deletedDraftIds.add(draftId);
    return const CreateDraftStoreState();
  }

  @override
  Future<CreateDraftStoreState> load() async {
    return const CreateDraftStoreState();
  }

  @override
  Future<CreateDraft?> loadDraft(String draftId) async => null;

  @override
  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId) async {
    return const CreateDraftStoreState();
  }

  @override
  Future<CreateDraftStoreState> upsertDraft(
    CreateDraft draft, {
    String? currentDraftId,
  }) async {
    return const CreateDraftStoreState();
  }
}
