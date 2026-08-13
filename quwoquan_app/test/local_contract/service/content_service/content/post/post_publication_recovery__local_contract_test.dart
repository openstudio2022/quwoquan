// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-004.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-007
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show CreationText;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show createContentPostPublicationWriterProvider;
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryReporterProvider;
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_draft_local_storage.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/post_publication_task_section.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';
import '../../../../../support/service/content_service/content/post/recording_content_post_publication_writer.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

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
      contentType: ContentType.micro,
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

    // GWT-007 单轨与脱敏负例：发布链路只提交强类型 content_publication
    // 产品遥测（不得混入推荐行为 ReportBehaviors 通道的事件），且事件
    // 不携带正文与原始 intentId（只允许 correlationHash 派生值）。
    final publicationEvents = recoveredTelemetry.recorded
        .where((event) => event.eventType == 'content_publication')
        .toList(growable: false);
    expect(publicationEvents, isNotEmpty);
    expect(
      recoveredTelemetry.recorded.map((event) => event.eventType).toSet(),
      <String>{'content_publication'},
      reason: '发布恢复链路不得经任何第二遥测通道（如推荐行为上报）发事件',
    );
    for (final event in publicationEvents) {
      expect(event.extensions.containsKey('body'), isFalse);
      expect(event.extensions.containsKey('publishIntentId'), isFalse);
      expect(
        event.extensions.values.whereType<String>(),
        isNot(contains('intent-recovery')),
        reason: '原始 intentId 不得进入遥测扩展字段',
      );
    }
  });

  // spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
  test('弱网五段旅程：断网入队→杀进程→恢复→media_not_ready 轮询→发布回读', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final draftRepository = SharedPreferencesCreateDraftRepository(
      scopeKey: CreateDraftLocalStorage.scopeKeyForUser('user-publication'),
    );
    await draftRepository.upsertDraft(
      CreateDraft(
        id: 'draft-weak-net',
        updatedAtMs: DateTime.utc(2026, 8, 12).millisecondsSinceEpoch,
        state: CreateEditorState.initial().copyWith(
          draftId: 'draft-weak-net',
          body: '弱网下也不丢失的发布',
        ),
      ),
    );
    final command = SubmitContentPostPublicationCommand(
      publishIntentId: 'intent-weak-net',
      localDraftId: 'draft-weak-net',
      contentType: ContentType.micro,
      body: '弱网下也不丢失的发布',
    );

    // 段 1：断网提交 → 意图入队持久化，草稿保留，不静默丢失。
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
    expect(offlineWriter.commands, hasLength(1));
    expect((await draftRepository.load()).drafts, hasLength(1));

    // 段 2：杀进程（容器销毁，只有持久化状态存活）。
    firstProcess.dispose();

    // 段 3+4：重启恢复同一意图；服务端先答 media_not_ready（transient，
    // recovery=retry），队列按轮询语义继续尝试而不是永久阻断。
    final flakyWriter = _MediaNotReadyThenPublishedWriter(
      failuresBeforeSuccess: 2,
    );
    final restartedProcess = _container(
      writer: flakyWriter,
      drafts: draftRepository,
    );
    addTearDown(restartedProcess.dispose);
    restartedProcess.read(postPublicationIntentQueueProvider);
    final restartedNotifier = restartedProcess.read(
      postPublicationIntentQueueProvider.notifier,
    );

    // 轮询驱动与后台重试同语义：反复 flush 到期意图直至发布收敛。
    // recovery-after 1s × 2 次失败 → 收敛窗口须覆盖服务端指示的退避。
    await _waitUntil(() async {
      await restartedNotifier.flushNow();
      final drafts = await draftRepository.load();
      return flakyWriter.publishedCommands.length == 1 &&
          drafts.drafts.isEmpty &&
          restartedProcess
              .read(postPublicationIntentQueueProvider)
              .intents
              .isEmpty;
    }, attempts: 600, interval: const Duration(milliseconds: 20));

    // 段 5：发布回读——同一不可变意图跨进程/跨失败重放，回执携带 canonical
    // postId，草稿删除、队列清空。
    expect(flakyWriter.commands.length, greaterThanOrEqualTo(3));
    expect(
      flakyWriter.commands.map((c) => c.publishIntentId).toSet(),
      <String>{'intent-weak-net'},
      reason: '断网/轮询期间的每次重放必须复用首次不可变意图',
    );
    expect(
      flakyWriter.publishedCommands.single.localDraftId,
      'draft-weak-net',
    );
    expect(flakyWriter.lastReceipt?.postId, 'post-draft-weak-net');
    expect(flakyWriter.lastReceipt?.state, 'published');
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
      contentType: ContentType.micro,
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
          personaId: 'persona-publication',
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

Future<void> _waitUntil(
  Future<bool> Function() condition, {
  int attempts = 300,
  Duration interval = const Duration(milliseconds: 10),
}) async {
  for (var attempt = 0; attempt < attempts; attempt++) {
    if (await condition()) {
      return;
    }
    await Future<void>.delayed(interval);
  }
  fail('发布意图未在进程重启后自动完成');
}

final class _OfflinePublicationWriter implements ContentPostPublicationWriter {
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

/// 服务端媒体处理未就绪的轮询语义：先按 `CONTENT.USER.media_not_ready`
/// （transient / recovery=retry）拒绝 N 次，之后受理并发布。
final class _MediaNotReadyThenPublishedWriter
    implements ContentPostPublicationWriter {
  _MediaNotReadyThenPublishedWriter({required this.failuresBeforeSuccess});

  int failuresBeforeSuccess;
  final List<SubmitContentPostPublicationCommand> commands =
      <SubmitContentPostPublicationCommand>[];
  final List<SubmitContentPostPublicationCommand> publishedCommands =
      <SubmitContentPostPublicationCommand>[];
  PostPublicationReceipt? lastReceipt;

  @override
  Future<PostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  ) async {
    commands.add(command);
    if (failuresBeforeSuccess > 0) {
      failuresBeforeSuccess -= 1;
      throw CloudException(
        type: CloudErrorType.invalidResponse,
        message: 'media is processing',
        code: 'CONTENT.USER.media_not_ready',
        runtimeFailure: testRuntimeFailure(
          code: 'CONTENT.USER.media_not_ready',
          nature: RuntimeFailureNature.transient,
          recovery: const RuntimeRecoveryDirective(
            action: 'retry',
            afterSeconds: 1,
            disruptionLevel: 'silent',
          ),
        ),
      );
    }
    publishedCommands.add(command);
    final receipt = PostPublicationReceipt(
      publishIntentId: command.publishIntentId,
      localDraftId: command.localDraftId,
      postId: 'post-${command.localDraftId}',
      state: 'published',
      committedVersion: 1,
      acceptedAt: DateTime.utc(2026, 8, 12),
    );
    lastReceipt = receipt;
    return receipt;
  }
}
