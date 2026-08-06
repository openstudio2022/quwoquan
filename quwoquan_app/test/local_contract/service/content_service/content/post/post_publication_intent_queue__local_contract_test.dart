import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_preparation_checkpoint.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';
import '../../../../../support/runtime/transport/recording_content_media_facet.dart';

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
      'post_publication_intents:user-publication',
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
          contentType: ContentType.micro,
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
      command: _command(contentType: ContentType.image),
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
        'post_publication_intents:user-publication',
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
      command: _command(contentType: ContentType.video),
      authorPersonaId: 'persona-publication',
    );
    const sourceBytes = 'video-source-bytes:draft-1:video:0';
    final sourceDigest = _sha256Digest(sourceBytes);
    await notifier.recordPreparedMediaAsset(
      'draft-1',
      _checkpointForSource(
        preparationIdentity: 'draft-1',
        slot: 'video:0',
        mediaType: MediaType.video,
        sha256Digest: sourceDigest,
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
    expect(checkpoint.mediaType, MediaType.video);
    expect(checkpoint.sha256Digest, sourceDigest);
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
      command: _command(contentType: ContentType.video),
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = _checkpointForSource(
      preparationIdentity: 'draft-1',
      slot: 'video:0',
      mediaType: MediaType.video,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: MediaType.video,
        mimeType: 'video/mp4',
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
      command: _command(contentType: ContentType.image),
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = _checkpointForSource(
      preparationIdentity: 'draft-1',
      slot: 'image:0',
      mediaType: MediaType.image,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: MediaType.image,
        mimeType: 'image/jpeg',
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
    final command = _command(contentType: ContentType.image);
    await notifier.beginMediaPreparation(
      command: command,
      authorPersonaId: 'persona-publication',
    );
    final checkpoint = _checkpointForSource(
      preparationIdentity: 'draft-1',
      slot: 'image:0',
      mediaType: MediaType.image,
      sha256Digest: 'sha256:$_pendingVideoDigest',
    );
    final initialized = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: MediaType.image,
        mimeType: 'image/jpeg',
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
      completedAssetStatus: MediaAssetStatus.processing,
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
    final command = _command(contentType: ContentType.image);
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
      completedAssetStatus: MediaAssetStatus.rejected,
    );
    final writer = _SuccessfulPublicationWriter();
    final drafts = _RecordingDraftRepository();
    final container = _container(writer: writer, drafts: drafts, media: media);
    addTearDown(container.dispose);
    final notifier = container.read(
      postPublicationIntentQueueProvider.notifier,
    );
    final command = _command(contentType: ContentType.image);
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

  test('发布后 continuation 先于草稿删除且跨进程重试保持同一来源', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final events = <String>[];
    final drafts = _ContinuationDraftRepository(
      draft: _continuationDraft(),
      events: events,
    );
    final firstHandler = _RecordingContinuationHandler(
      events: events,
      fail: true,
    );
    final first = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: drafts,
      continuationRegistry: PostPublicationContinuationRegistry(
        <PostPublicationContinuationHandler>[firstHandler],
      ),
    );

    final receipt = await first
        .read(postPublicationIntentQueueProvider.notifier)
        .submit(command: _command(), authorPersonaId: 'persona-publication');

    expect(receipt.state, 'published');
    expect(events, <String>['continuation']);
    expect(drafts.deletedDraftIds, isEmpty);
    final pending = first
        .read(postPublicationIntentQueueProvider)
        .intents
        .single;
    expect(pending.publicationState, ContentPostPublicationState.published);
    expect(pending.blocked, isFalse);
    expect(
      pending.publicationContinuation?.sourceEntityRef,
      'travel.TripShareSnapshot:share-1@2',
    );
    first.dispose();

    final recoveredHandler = _RecordingContinuationHandler(events: events);
    final recovered = _container(
      writer: _SuccessfulPublicationWriter(),
      drafts: drafts,
      continuationRegistry: PostPublicationContinuationRegistry(
        <PostPublicationContinuationHandler>[recoveredHandler],
      ),
    );
    addTearDown(recovered.dispose);
    recovered.read(postPublicationIntentQueueProvider);
    await _waitForHydration(recovered);
    await recovered
        .read(postPublicationIntentQueueProvider.notifier)
        .retryPending('draft-1');

    expect(events, <String>['continuation', 'continuation', 'delete']);
    expect(drafts.deletedDraftIds, <String>['draft-1']);
    expect(recovered.read(postPublicationIntentQueueProvider).intents, isEmpty);
    expect(
      recoveredHandler.receipts.single.committedVersion,
      receipt.committedVersion,
    );
  });
}

const String _pendingVideoDigest =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

String _sha256Digest(String payload) =>
    'sha256:${sha256.convert(utf8.encode(payload))}';

ProviderContainer _container({
  required ContentPostPublicationWriter writer,
  required CreateDraftRepository drafts,
  ContentPostPublicationStatusReader? statusReader,
  ContentMediaFacet? media,
  PostPublicationContinuationRegistry? continuationRegistry,
}) {
  return ProviderContainer(
    overrides: [
      currentUserIdProvider.overrideWithValue('user-publication'),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'persona-publication',
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
      if (continuationRegistry != null)
        postPublicationContinuationRegistryProvider.overrideWithValue(
          continuationRegistry,
        ),
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
  final checkpoint = _checkpointForSource(
    preparationIdentity: command.localDraftId,
    slot: 'image:0',
    mediaType: MediaType.image,
    sha256Digest: 'sha256:$_pendingVideoDigest',
  );
  final initialized = await media.initUpload(
    InitContentMediaUploadCommand(
      mediaType: MediaType.image,
      mimeType: 'image/jpeg',
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
  ContentType contentType = ContentType.micro,
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
  Future<PostPublicationReceipt> submitPostPublication(
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
  Future<PostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    return PostPublicationReceipt(
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
  Future<PostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    return PostPublicationReceipt(
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
  Future<PostPublicationReceipt> submitPostPublication(
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

ContentMediaPreparationCheckpoint _checkpointForSource({
  required String preparationIdentity,
  required String slot,
  required MediaType mediaType,
  required String sha256Digest,
  int attempt = 0,
}) {
  final identity =
      '$preparationIdentity:$slot:${mediaType.name}:$sha256Digest:$attempt';
  return ContentMediaPreparationCheckpoint(
    slot: slot,
    mediaType: mediaType,
    sha256Digest: sha256Digest,
    assetId: '',
    initIdempotencyKey: 'test-init:$identity',
    completeIdempotencyKey: 'test-complete:$identity',
    abortIdempotencyKey: 'test-abort:$identity',
    discardIdempotencyKey: 'test-discard:$identity',
    attempt: attempt,
  );
}

CreateDraft _continuationDraft() => CreateDraft(
  id: 'draft-1',
  updatedAtMs: 1,
  state: CreateEditorState.initial().copyWith(draftId: 'draft-1'),
  sourceType: 'article',
  publicationContinuation: const CreateDraftPublicationContinuationRef(
    operationId: 'travel.content_link.put',
    sourceEntityRef: 'travel.TripShareSnapshot:share-1@2',
  ),
);

final class _ContinuationDraftRepository implements CreateDraftRepository {
  _ContinuationDraftRepository({required this.draft, required this.events});

  CreateDraft? draft;
  final List<String> events;
  final List<String> deletedDraftIds = <String>[];

  @override
  Future<CreateDraftStoreState> deleteDraft(String draftId) async {
    events.add('delete');
    deletedDraftIds.add(draftId);
    draft = null;
    return const CreateDraftStoreState();
  }

  @override
  Future<CreateDraftStoreState> load() async => CreateDraftStoreState(
    drafts: draft == null ? const <CreateDraft>[] : <CreateDraft>[draft!],
    currentDraftId: draft?.id,
  );

  @override
  Future<CreateDraft?> loadDraft(String draftId) async =>
      draft?.id == draftId ? draft : null;

  @override
  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId) => load();

  @override
  Future<CreateDraftStoreState> upsertDraft(
    CreateDraft draft, {
    String? currentDraftId,
  }) async {
    this.draft = draft;
    return load();
  }
}

final class _RecordingContinuationHandler
    implements PostPublicationContinuationHandler {
  _RecordingContinuationHandler({required this.events, this.fail = false});

  final List<String> events;
  final bool fail;
  final List<PostPublicationReceipt> receipts = <PostPublicationReceipt>[];

  @override
  String get operationId => 'travel.content_link.put';

  @override
  Future<void> apply({
    required CreateDraftPublicationContinuationRef continuation,
    required PostPublicationReceipt receipt,
  }) async {
    events.add('continuation');
    receipts.add(receipt);
    if (fail) {
      throw StateError('temporary continuation failure');
    }
  }
}
