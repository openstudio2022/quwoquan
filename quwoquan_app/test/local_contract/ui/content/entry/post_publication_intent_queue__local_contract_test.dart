import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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
}

ProviderContainer _container({
  required ContentPostPublicationWriter writer,
  required CreateDraftRepository drafts,
  ContentPostPublicationStatusReader? statusReader,
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

SubmitContentPostPublicationCommand _command() {
  return SubmitContentPostPublicationCommand(
    publishIntentId: 'intent-1',
    localDraftId: 'draft-1',
    contentType: ContentPostType.micro,
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
