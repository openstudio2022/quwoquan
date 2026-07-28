import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/post_publication_task_section.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../support/recording_content_post_publication_writer.dart';
import '../../../../support/recording_app_telemetry_recorder.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('断网重启后会恢复一次本地发布意图', () async {
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
    final offlineTelemetry = RecordingAppTelemetryRecorder();
    final firstProcess = _container(
      writer: offlineWriter,
      drafts: draftRepository,
      telemetry: offlineTelemetry,
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
    final recoveredTelemetry = RecordingAppTelemetryRecorder();
    final restartedProcess = _container(
      writer: recoveredWriter,
      drafts: draftRepository,
      telemetry: recoveredTelemetry,
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
    final retryTerminal = recoveredTelemetry.recorded.singleWhere(
      (event) =>
          event.eventType == 'content_publication' &&
          event.extensions['backgroundRetryTerminal'] == 'published',
    );
    expect(retryTerminal.extensions['publicationStage'], 'published');
    expect(retryTerminal.extensions['correlationHash'], isNotEmpty);
    expect(retryTerminal.extensions['durationMs'], isA<int>());
  });

  testWidgets('待恢复发布任务展示状态与重试入口', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final process = _container(
      writer: _OfflinePublicationWriter(),
      drafts: SharedPreferencesCreateDraftRepository(
        scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user-publication'),
      ),
    );
    final command = SubmitContentPostPublicationCommand(
      publishIntentId: 'intent-visible-recovery',
      localDraftId: 'draft-visible-recovery',
      contentType: ContentPostType.micro,
      body: '可见的待恢复发布任务',
    );
    await expectLater(
      process
          .read(postPublicationIntentQueueProvider.notifier)
          .submit(command: command, authorPersonaId: 'persona-publication'),
      throwsA(isA<PostPublicationQueuedException>()),
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: process,
        child: const CupertinoApp(home: _PublicationRecoverySurface()),
      ),
    );

    expect(find.text(CreationText.publishTasksTitle), findsOneWidget);
    expect(
      find.text(CreationText.publishTaskRetryWaitingStatus),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>('publication_task_retry_draft-visible-recovery'),
      ),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>(
          'publication_task_remove_draft-visible-recovery',
        ),
      ),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox.shrink());
    process.dispose();
  });
}

final class _PublicationRecoverySurface extends ConsumerWidget {
  const _PublicationRecoverySurface();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(postPublicationIntentQueueProvider);
    return CupertinoPageScaffold(
      child: SafeArea(
        child: PostPublicationTaskSection(
          intents: state.intents,
          onRetry: (intent) {
            unawaited(
              ref
                  .read(postPublicationIntentQueueProvider.notifier)
                  .retryPending(intent.command.localDraftId),
            );
          },
          onEdit: (_) {},
          onRemove: (intent) {
            unawaited(
              ref
                  .read(postPublicationIntentQueueProvider.notifier)
                  .cancelPending(intent.command.localDraftId),
            );
          },
        ),
      ),
    );
  }
}

ProviderContainer _container({
  required ContentPostPublicationWriter writer,
  required CreateDraftRepository drafts,
  RecordingAppTelemetryRecorder? telemetry,
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
      if (telemetry != null)
        appTelemetryReporterProvider.overrideWithValue(telemetry),
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
