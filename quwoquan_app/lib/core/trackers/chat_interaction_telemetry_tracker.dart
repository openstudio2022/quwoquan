import 'dart:developer' as developer;

import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/runtime_failure_telemetry_dimensions.dart';

/// 群聊商业漏斗的唯一端侧写入器。
///
/// 只暴露 metadata 枚举的动作、结果和分桶；会话、消息、成员等业务标识不得进入
/// telemetry payload，避免严格 `/ops/events` 协议与服务端分析维度漂移。
enum ChatInteractionAction {
  candidateSourceOpen,
  candidateSourceSelect,
  groupCreate,
  memberAdd,
  mentionSelect,
  mentionSend,
  readWatermark,
  groupGovernance,
}

enum ChatInteractionOutcome {
  succeeded,
  failed,
  rejected,
  cancelled,
  unchanged,
}

enum ChatInteractionSource {
  contacts,
  group,
  circle,
  roster,
  composer,
  conversation,
  settings,
}

enum ChatMentionScope { none, member, all, assistant }

enum ChatGovernanceAction {
  none,
  announcementUpdate,
  adminAssign,
  adminRevoke,
  ownershipTransfer,
  memberRemove,
  memberLeave,
}

enum ChatWatermarkResult { none, advanced, alreadyCurrent, rejected, failed }

extension on ChatInteractionAction {
  String get wireValue => switch (this) {
    ChatInteractionAction.candidateSourceOpen => 'candidate_source_open',
    ChatInteractionAction.candidateSourceSelect => 'candidate_source_select',
    ChatInteractionAction.groupCreate => 'group_create',
    ChatInteractionAction.memberAdd => 'member_add',
    ChatInteractionAction.mentionSelect => 'mention_select',
    ChatInteractionAction.mentionSend => 'mention_send',
    ChatInteractionAction.readWatermark => 'read_watermark',
    ChatInteractionAction.groupGovernance => 'group_governance',
  };
}

extension on ChatInteractionOutcome {
  String get wireValue => switch (this) {
    ChatInteractionOutcome.succeeded => 'succeeded',
    ChatInteractionOutcome.failed => 'failed',
    ChatInteractionOutcome.rejected => 'rejected',
    ChatInteractionOutcome.cancelled => 'cancelled',
    ChatInteractionOutcome.unchanged => 'unchanged',
  };
}

extension on ChatInteractionSource {
  String get wireValue => switch (this) {
    ChatInteractionSource.contacts => 'contacts',
    ChatInteractionSource.group => 'group',
    ChatInteractionSource.circle => 'circle',
    ChatInteractionSource.roster => 'roster',
    ChatInteractionSource.composer => 'composer',
    ChatInteractionSource.conversation => 'conversation',
    ChatInteractionSource.settings => 'settings',
  };
}

extension on ChatMentionScope {
  String get wireValue => switch (this) {
    ChatMentionScope.none => 'none',
    ChatMentionScope.member => 'member',
    ChatMentionScope.all => 'all',
    ChatMentionScope.assistant => 'assistant',
  };
}

extension on ChatGovernanceAction {
  String get wireValue => switch (this) {
    ChatGovernanceAction.none => 'none',
    ChatGovernanceAction.announcementUpdate => 'announcement_update',
    ChatGovernanceAction.adminAssign => 'admin_assign',
    ChatGovernanceAction.adminRevoke => 'admin_revoke',
    ChatGovernanceAction.ownershipTransfer => 'ownership_transfer',
    ChatGovernanceAction.memberRemove => 'member_remove',
    ChatGovernanceAction.memberLeave => 'member_leave',
  };
}

extension on ChatWatermarkResult {
  String get wireValue => switch (this) {
    ChatWatermarkResult.none => 'none',
    ChatWatermarkResult.advanced => 'advanced',
    ChatWatermarkResult.alreadyCurrent => 'already_current',
    ChatWatermarkResult.rejected => 'rejected',
    ChatWatermarkResult.failed => 'failed',
  };
}

final class ChatInteractionTelemetryTracker {
  ChatInteractionTelemetryTracker({required this.telemetryReporter});

  final AppTelemetryRecorder telemetryReporter;

  Future<void> track({
    required ChatInteractionAction action,
    required ChatInteractionOutcome outcome,
    required String pageName,
    required String surfaceId,
    ChatInteractionSource? source,
    ChatMentionScope? mentionScope,
    ChatGovernanceAction? governanceAction,
    ChatWatermarkResult? watermarkResult,
    int? memberCount,
    int? unreadCount,
    Duration? duration,
    Object? error,
  }) async {
    final dimensions = RuntimeFailureTelemetryDimensions.from(error);
    try {
      await telemetryReporter.record(
        AppTelemetryPayload.chatInteractionOutcome(
          chatAction: action.wireValue,
          chatOutcome: outcome.wireValue,
          chatSource: source?.wireValue,
          mentionScope: mentionScope?.wireValue,
          governanceAction: governanceAction?.wireValue,
          watermarkResult: watermarkResult?.wireValue,
          memberCountBucket: memberCount == null
              ? null
              : _countBucket(memberCount),
          unreadCountBucket: unreadCount == null
              ? null
              : _countBucket(unreadCount),
          surfaceId: surfaceId,
          durationMs: duration?.inMilliseconds,
          failReasonCode: dimensions.sourceCode.isEmpty
              ? null
              : dimensions.sourceCode,
          recoveryAction: dimensions.recoveryAction.isEmpty
              ? null
              : dimensions.recoveryAction,
        ),
        pageName: pageName,
      );
    } catch (error, stackTrace) {
      developer.log(
        'ChatInteractionTelemetryTracker.track failed',
        name: 'ChatInteractionTelemetryTracker',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  String _countBucket(int value) {
    if (value <= 0) return 'zero';
    if (value == 1) return 'one';
    if (value <= 5) return 'two_to_five';
    if (value <= 50) return 'six_to_fifty';
    if (value <= 500) return 'fifty_one_to_five_hundred';
    return 'five_hundred_one_to_one_thousand';
  }
}
