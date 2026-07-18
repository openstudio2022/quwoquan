import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../support/recording_content_post_publication_writer.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('断网并重启后无需再次点击即可完成原发布意图', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final draftRepository = SharedPreferencesCreateDraftRepository(
      scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user-publication'),
    );
    await draftRepository.upsertDraft(
      CreateDraft(
        id: 'draft-recovery',
        updatedAtMs: DateTime.utc(2026, 7, 17).millisecondsSinceEpoch,
        state: CreateEditorState.initial(
          editorKind: CreateEditorKind.media,
        ).copyWith(draftId: 'draft-recovery', body: '只点击一次也能安全发布'),
      ),
    );
    final command = SubmitContentPostPublicationCommand(
      publishIntentId: 'intent-recovery',
      localDraftId: 'draft-recovery',
      contentType: ContentPostType.micro,
      body: '只点击一次也能安全发布',
    );

    final offlineWriter = _OfflinePublicationWriter();
    final firstProcess = _container(
      writer: offlineWriter,
      drafts: draftRepository,
    );
    await expectLater(
      firstProcess
          .read(postPublicationIntentQueueProvider.notifier)
          .submit(command: command, authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationQueuedException>()),
    );
    expect((await draftRepository.load()).drafts, hasLength(1));
    expect(offlineWriter.commands, hasLength(1));
    firstProcess.dispose();

    final recoveredWriter = RecordingContentPostPublicationWriter();
    final restartedProcess = _container(
      writer: recoveredWriter,
      drafts: draftRepository,
    );
    addTearDown(restartedProcess.dispose);
    restartedProcess.read(postPublicationIntentQueueProvider);

    await _waitUntil(() async {
      final drafts = await draftRepository.load();
      return recoveredWriter.submitCommands.length == 1 &&
          drafts.drafts.isEmpty &&
          restartedProcess
              .read(postPublicationIntentQueueProvider)
              .intents
              .isEmpty;
    });

    expect(
      recoveredWriter.submitCommands.single.publishIntentId,
      'intent-recovery',
    );
    expect(
      recoveredWriter.submitCommands.single.localDraftId,
      'draft-recovery',
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

Future<void> _waitUntil(Future<bool> Function() condition) async {
  for (var attempt = 0; attempt < 300; attempt++) {
    if (await condition()) {
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('发布意图未在进程重启后自动完成');
}

final class _OfflinePublicationWriter implements ContentPostPublicationWriter {
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
