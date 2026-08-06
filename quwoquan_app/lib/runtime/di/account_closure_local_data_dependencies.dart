import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/adapters/assistant_consent_store.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/public/skill_consent_terminal_account_purger.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_draft_store.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_draft_terminal_account_purger.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_outbox_adapter.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_outbox_terminal_account_purger.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_draft_local_storage.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_publication_intent_local_storage.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/secure_interest_onboarding_draft_store.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_terminal_account_purgers.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/incoming_call_terminal_account_purger.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/account_closure_local_data_purger.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/design_system/emoji/emoji_providers.dart';
import 'package:quwoquan_app/runtime/platform/temporary_file_cleanup.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';

/// 主动注销路径在 auth 状态切换前读取，固定本次 closed actor 身份。
final accountClosureLocalDataPurgerProvider =
    Provider<AccountClosureLocalDataPurger>((ref) {
      final actor = AccountClosureLocalActorContext.fromSession(
        ref.read(authSessionControllerProvider),
      );
      return ref.read(accountClosureLocalDataPurgerForActorProvider(actor));
    });

final accountClosureLocalDataPurgerForActorProvider =
    Provider.family<
      AccountClosureLocalDataPurger,
      AccountClosureLocalActorContext
    >(_createAccountClosureLocalDataPurger);

final accountClosureLocalCleanupRecoveryProvider =
    Provider<Future<void> Function()>((ref) {
      Future<void>? inFlight;
      var rerunRequested = false;

      Future<void> recover() {
        final active = inFlight;
        if (active != null) {
          rerunRequested = true;
          return active;
        }
        final task = () async {
          do {
            rerunRequested = false;
            await _recoverPendingTerminalAccountCleanup(ref);
          } while (rerunRequested);
        }();
        inFlight = task;
        return task.whenComplete(() {
          if (identical(inFlight, task)) {
            inFlight = null;
          }
        });
      }

      return recover;
    });

/// 处理“其他设备已注销 / 主动注销成功后进程崩溃”的恢复路径。
final accountClosureLocalCleanupLifecycleProvider = Provider<void>((ref) {
  final recover = ref.watch(accountClosureLocalCleanupRecoveryProvider);
  unawaited(recover());
  ref.listen<AuthSessionState>(authSessionControllerProvider, (previous, next) {
    if (previous?.isAuthenticated != true ||
        next.promptReason != AuthPromptReason.accountClosed) {
      return;
    }
    unawaited(recover());
  });
});

AccountClosureLocalDataPurger _createAccountClosureLocalDataPurger(
  Ref ref,
  AccountClosureLocalActorContext actor,
) {
  final closureActorId = actor.personaId.isNotEmpty
      ? actor.personaId
      : actor.accountId;
  final runtimeLogBuffer = ref.read(runtimeLogBufferProvider);
  final queueStorage = ref.read(actorQueueStorageProvider);
  final cacheManagement = ref.read(cacheManagementServiceProvider);
  final emojiRepositoryFuture = ref.read(emojiRepositoryProvider.future);
  final visitRecorder = ref.read(visitRecorderServiceProvider);
  final mediaUploadManager = ref.read(mediaUploadManagerProvider);
  final closureQueuePartition = ActorQueuePartition(
    environment: CloudRuntimeConfig.appRuntimeEnv,
    accountId: actor.accountId,
    personaId: actor.personaId,
    deviceId: (CloudRequestHeaders.deviceActorId ?? '').trim().isNotEmpty
        ? CloudRequestHeaders.deviceActorId!
        : actor.installId,
  );
  final ContentBehaviorOutboxTerminalAccountPurger behaviorOutboxPurger =
      ActorScopedContentBehaviorOutboxPurger(
        closureQueuePartition,
        queueStorage,
      );
  final SkillConsentTerminalAccountPurger assistantConsentPurger =
      AssistantConsentStore(accountId: actor.accountId);
  final CommentDraftTerminalAccountPurger commentDraftPurger =
      CommentDraftStore(actorScope: closureActorId);
  final CreateDraftTerminalAccountPurger createDraftPurger =
      CreateDraftLocalStorage.forTerminalAccountClosure(closureActorId);
  final PostPublicationIntentTerminalAccountPurger publicationIntentPurger =
      PostPublicationIntentLocalStorage.forTerminalAccountClosure(
        closureActorId,
      );
  final InterestOnboardingDraftTerminalAccountPurger interestDraftPurger =
      const SecureInterestOnboardingDraftStore();
  final IncomingCallTerminalAccountPurger incomingCallPurger = ref.read(
    incomingCallCoordinatorProvider,
  );

  return AccountClosureLocalDataPurger(
    clearBehaviorQueue: behaviorOutboxPurger.purgeForTerminalAccountClosure,
    clearTelemetryQueue: () => Future.wait<void>(<Future<void>>[
      queueStorage.purge(closureQueuePartition, kAppTelemetryOutboxName),
      queueStorage.purge(
        closureQueuePartition,
        kAssistantLearningFactOutboxName,
      ),
      runtimeLogBuffer.clear(),
    ]),
    clearRebuildableUserData: cacheManagement.clearForTerminalAccountClosure,
    purgePushAndIncomingCallState:
        incomingCallPurger.purgeForTerminalAccountClosure,
    clearDraftsAndAccountPreferences: () async {
      try {
        await Future.wait<void>(<Future<void>>[
          Future<void>.sync(
            () => ref
                .read(clientStateSyncOutboxProvider.notifier)
                .purgeForTerminalAccountClosure(),
          ),
          Future<void>.sync(createDraftPurger.purgeForTerminalAccountClosure),
          Future<void>.sync(
            publicationIntentPurger.purgeForTerminalAccountClosure,
          ),
          Future<void>.sync(commentDraftPurger.purgeForTerminalAccountClosure),
          Future<void>.sync(
            assistantConsentPurger.purgeForTerminalAccountClosure,
          ),
          Future<void>.sync(
            () => emojiRepositoryFuture.then(
              (repository) => repository.clearForTerminalAccountClosure(),
            ),
          ),
          Future<void>.sync(
            () => ref
                .read(chatSendOutboxControlProvider)
                .purgeForTerminalAccountClosure(),
          ),
          Future<void>.sync(visitRecorder.clearForTerminalAccountClosure),
          Future<void>.sync(interestDraftPurger.purgeForTerminalAccountClosure),
          Future<void>.sync(
            () => ref
                .read(desktopPickerDirectoryMemoryProvider)
                .clearForTerminalAccountClosure(),
          ),
          Future<void>.sync(
            clearClientInteractionStateForTerminalAccountClosure,
          ),
          Future<void>.sync(mediaUploadManager.dispose),
          Future<void>.sync(
            clearAppTemporaryDirectoryForTerminalAccountClosure,
          ),
        ]);
      } finally {
        ref.invalidate(userRelationshipStateProvider);
        ref.invalidate(postInteractionStateProvider);
        ref.invalidate(clientStateSyncOutboxProvider);
        ref.invalidate(mediaUploadManagerProvider);
        resetChatSendOutbox(ref);
        ref.invalidate(visitRecorderServiceProvider);
      }
    },
  );
}

Future<void> _recoverPendingTerminalAccountCleanup(Ref ref) async {
  final receiptStore = ref.read(terminalAccountCleanupReceiptStoreProvider);
  try {
    final receipt = await receiptStore.read();
    if (receipt == null) {
      return;
    }
    final actor = AccountClosureLocalActorContext.fromReceipt(receipt);
    final purger = ref.read(
      accountClosureLocalDataPurgerForActorProvider(actor),
    );
    if (!await _purgeDetectedTerminalAccount(purger)) {
      return;
    }
    await receiptStore.clear();
    ref.invalidate(accountClosureLocalDataPurgerForActorProvider(actor));
  } catch (error, stackTrace) {
    await AppExceptionTelemetryService.instance.recordHandledException(
      source: 'account_closure_local_cleanup_recovery',
      error: error,
      stackTrace: stackTrace,
    );
  }
}

Future<bool> _purgeDetectedTerminalAccount(
  AccountClosureLocalDataPurger purger,
) async {
  Object? lastError;
  StackTrace? lastStackTrace;
  for (var attempt = 0; attempt < 3; attempt++) {
    try {
      await purger.purge();
      return true;
    } catch (error, stackTrace) {
      lastError = error;
      lastStackTrace = stackTrace;
      if (attempt < 2) {
        await Future<void>.delayed(
          Duration(milliseconds: 100 * (1 << attempt)),
        );
      }
    }
  }
  await AppExceptionTelemetryService.instance.recordHandledException(
    source: 'account_closure_detected_local_privacy_cleanup',
    error: lastError!,
    stackTrace: lastStackTrace!,
  );
  return false;
}

final class AccountClosureLocalActorContext {
  const AccountClosureLocalActorContext({
    required this.accountId,
    required this.personaId,
    required this.installId,
  });

  factory AccountClosureLocalActorContext.fromSession(
    AuthSessionState session,
  ) {
    final accountId = session.ownerId.trim();
    if (!session.isAuthenticated || accountId.isEmpty) {
      throw StateError(
        'terminal account cleanup requires the authenticated previous actor',
      );
    }
    return AccountClosureLocalActorContext(
      accountId: accountId,
      personaId: session.activePersonaId.trim(),
      installId: session.installId.trim(),
    );
  }

  factory AccountClosureLocalActorContext.fromReceipt(
    TerminalAccountCleanupReceipt receipt,
  ) {
    return AccountClosureLocalActorContext(
      accountId: receipt.accountId.trim(),
      personaId: receipt.personaId.trim(),
      installId: receipt.installId.trim(),
    );
  }

  final String accountId;
  final String personaId;
  final String installId;

  @override
  bool operator ==(Object other) {
    return other is AccountClosureLocalActorContext &&
        other.accountId == accountId &&
        other.personaId == personaId &&
        other.installId == installId;
  }

  @override
  int get hashCode => Object.hash(accountId, personaId, installId);
}
