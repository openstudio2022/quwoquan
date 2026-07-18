import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
}

ProviderContainer _container({
  required ContentPostPublicationWriter writer,
  required CreateDraftRepository drafts,
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
