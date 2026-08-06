import 'dart:async';
import 'dart:collection';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String _patchLogName = 'FeedRealtimePatch';
const Object _unsetPolicyDigest = Object();

/// 单 channel 的实时 patch 展示态（强类型；不承载已剔除内容——
/// `negative_feedback_removal` 直接落 [DiscoveryFeedMapNotifier.removePostLocally]）。
///
/// `new_candidate_hint` / `refresh_suggestion` 仅在此处累积一个轻量提示，
/// 由顶部 pill 消费；不自动插入内容、不改变阅读位置。
class FeedRealtimePatchHint {
  const FeedRealtimePatchHint({
    required this.channelId,
    required this.reasonCode,
    this.newCandidateCount = 0,
    this.refreshSuggested = false,
    this.lastPatchId = '',
    this.feedRequestId,
    this.policyDigest,
  });

  final String channelId;

  /// 累积的「新候选」数量（`new_candidate_hint.affectedCount` 之和，>0 才展示计数）。
  final int newCandidateCount;

  /// 是否建议刷新（`refresh_suggestion`，或无计数的 `new_candidate_hint`）。
  final bool refreshSuggested;

  final FeedPatchReasonCode reasonCode;
  final String lastPatchId;

  /// 触发该提示的 feed 归因 id（与 [DiscoveryFeedState.feedRequestId] 对齐）。
  final String? feedRequestId;

  /// 触发最后一条 patch 的唯一推荐策略内容摘要。
  ///
  /// `null` 仅表示该 patch 来源未提供；非空值已由 wire parser
  /// 严格校验为 `sha256:<64 lowercase hex>`。
  final String? policyDigest;

  bool get hasUpdate => newCandidateCount > 0 || refreshSuggested;

  FeedRealtimePatchHint copyWith({
    int? newCandidateCount,
    bool? refreshSuggested,
    FeedPatchReasonCode? reasonCode,
    String? lastPatchId,
    String? feedRequestId,
    Object? policyDigest = _unsetPolicyDigest,
  }) {
    return FeedRealtimePatchHint(
      channelId: channelId,
      newCandidateCount: newCandidateCount ?? this.newCandidateCount,
      refreshSuggested: refreshSuggested ?? this.refreshSuggested,
      reasonCode: reasonCode ?? this.reasonCode,
      lastPatchId: lastPatchId ?? this.lastPatchId,
      feedRequestId: feedRequestId ?? this.feedRequestId,
      policyDigest: identical(policyDigest, _unsetPolicyDigest)
          ? this.policyDigest
          : policyDigest as String?,
    );
  }
}

/// 全量实时 patch 展示态（按 channelId 索引；强类型，不穿透弱类型 map）。
class FeedRealtimePatchState {
  const FeedRealtimePatchState({
    this.hints = const <String, FeedRealtimePatchHint>{},
  });

  final Map<String, FeedRealtimePatchHint> hints;

  FeedRealtimePatchHint? hintFor(String channelId) => hints[channelId];

  bool get hasAnyUpdate => hints.values.any((hint) => hint.hasUpdate);
}

/// 低风险实时推荐 patch 的端侧安全消费者（阶段 7）。
///
/// 订阅/传输由 realtime 层负责；本 notifier 只消费已解析的强类型
/// [FeedRealtimePatch]：按 `patchId` 幂等去重、按 `feedRequestId/channelId`
/// 对齐当前 feed、在不打断阅读位置的前提下安全合并到 `discovery_feed_provider`，
/// 并把 patch 生命周期（收到/展示/刷新/忽略/剔除）回流到统一埋点出口
/// [AnalyticsService]。
class FeedRealtimePatchNotifier extends Notifier<FeedRealtimePatchState> {
  /// 去重窗口上限：超出后淘汰最旧 patchId（有界内存，避免长会话无限增长）。
  static const int _maxTrackedPatchIds = 256;

  /// 已处理过的 patchId（FIFO 有界集合，实现幂等去重）。
  final LinkedHashSet<String> _appliedPatchIds = LinkedHashSet<String>();

  /// 当前已挂载（视口 + cacheExtent 内）的内容 id 集合。
  ///
  /// 由 feed 卡片在 `initState/dispose` 时上报，作为「正在阅读 / 视口内」的代理：
  /// 剔除仅作用于「位于所有已挂载项之下」的内容，保证不引发滚动跳动或卡片消失。
  final Set<String> _mountedPostIds = <String>{};

  @override
  FeedRealtimePatchState build() => const FeedRealtimePatchState();

  // ── 视口上报（仅内部字段变更，不触发 state 重建）───────────────────────────

  void setPostMounted(String postId, {required bool mounted}) {
    final id = postId.trim();
    if (id.isEmpty) {
      return;
    }
    if (mounted) {
      _mountedPostIds.add(id);
    } else {
      _mountedPostIds.remove(id);
    }
  }

  bool isPostMounted(String postId) => _mountedPostIds.contains(postId.trim());

  // ── patch 入口 ───────────────────────────────────────────────────────────

  /// 消费一条已解析的强类型实时 patch。
  ///
  /// 上游（realtime 层）负责 `parseFeedRealtimePatch`（schema 不符时 fail-closed 抛错并记录）；
  /// 此处完成鉴权门、幂等去重、feed 对齐与按类型的安全合并。
  void applyPatch(FeedRealtimePatch patch) {
    final policyDigest = patch.policyDigest;
    if (policyDigest != null && !isCanonicalSha256Digest(policyDigest)) {
      throw const FormatException(
        'policyDigest must be a canonical SHA-256 digest',
      );
    }
    // 1) 鉴权门：游客不消费；patch.userId 与当前用户不一致则忽略（防串号）。
    final currentUserId = _currentUserId();
    if (currentUserId.isEmpty) {
      return;
    }
    if (patch.userId.isNotEmpty && patch.userId != currentUserId) {
      return;
    }

    // 2) 幂等去重：缺失 patchId 无法去重，结构化记录并忽略。
    final patchId = patch.patchId.trim();
    if (patchId.isEmpty) {
      developer.log(
        'ignored feed patch with empty patchId (type=${patch.patchType.wire})',
        name: _patchLogName,
      );
      return;
    }
    if (_appliedPatchIds.contains(patchId)) {
      return;
    }

    // 3) 对齐当前 feed：按 feedRequestId / channelId 解析目标 channel；不匹配则忽略。
    final targetChannels = _resolveTargetChannels(patch);
    if (targetChannels.isEmpty) {
      _recordEvent('feed_patch_misaligned', patch);
      return;
    }

    _markPatchApplied(patchId);
    _recordEvent('feed_patch_received', patch, channels: targetChannels);

    switch (patch.patchType) {
      case FeedRealtimePatchType.negativeFeedbackRemoval:
        _applyRemoval(patch, targetChannels);
      case FeedRealtimePatchType.newCandidateHint:
        final delta = patch.affectedCount > 0 ? patch.affectedCount : 0;
        _applyHint(
          patch,
          targetChannels,
          candidateDelta: delta,
          refresh: delta == 0,
        );
      case FeedRealtimePatchType.refreshSuggestion:
        _applyHint(patch, targetChannels, refresh: true);
    }
  }

  // ── 用户主动交互 ───────────────────────────────────────────────────────────

  /// 用户点击「有更新」入口：记录刷新点击并清除该 channel 的提示。
  void acknowledgeRefresh(String channelId) {
    final hint = state.hints[channelId];
    if (hint == null) {
      return;
    }
    _recordHintEvent('feed_patch_refresh_clicked', channelId, hint);
    _clearHint(channelId);
  }

  /// 提示被忽略 / 失效（如切走、登出）：记录忽略并清除。
  void dismissHint(String channelId) {
    final hint = state.hints[channelId];
    if (hint == null) {
      return;
    }
    _recordHintEvent('feed_patch_dismissed', channelId, hint);
    _clearHint(channelId);
  }

  // ── 内部：对齐 ─────────────────────────────────────────────────────────────

  List<String> _resolveTargetChannels(FeedRealtimePatch patch) {
    final feedMap = ref.read(discoveryFeedMapProvider);
    final reqId = patch.feedRequestId?.trim() ?? '';
    final channelId = patch.channelId?.trim() ?? '';
    final targets = <String>[];
    for (final entry in feedMap.entries) {
      final value = entry.value.value;
      if (value == null) {
        continue;
      }
      final channelKey = entry.key;
      // channelId 对齐：patch 指定 channel 时必须等于客户端 channel key。
      if (channelId.isNotEmpty && channelId != channelKey) {
        continue;
      }
      // feedRequestId 对齐：patch 指定归因 id 时必须等于该 channel 当前 feed 的归因 id；
      // 不一致说明 patch 针对已过期的 feed 请求，忽略。
      if (reqId.isNotEmpty && reqId != (value.feedRequestId?.trim() ?? '')) {
        continue;
      }
      // policyDigest 一旦由 patch 提供，必须精确对齐该 channel 当前
      // feed 窗口；不做 trim、fallback 或跨请求沿用。
      if (patch.policyDigest != null &&
          patch.policyDigest != value.policyDigest) {
        continue;
      }
      targets.add(channelKey);
    }
    return targets;
  }

  // ── 内部：负反馈安全剔除（不打断阅读位置）─────────────────────────────────

  void _applyRemoval(FeedRealtimePatch patch, List<String> targetChannels) {
    final feedMap = ref.read(discoveryFeedMapProvider);
    final removableIds = <String>{};
    var deferredCount = 0;

    for (final channelKey in targetChannels) {
      final value = feedMap[channelKey]?.value;
      if (value == null) {
        continue;
      }
      final items = value.items;

      // 计算被「所有已挂载项之下」覆盖的安全下界：floor 为已挂载项的最大下标。
      // floor 之上（含视口与 cache）的匹配项一律暂缓，避免可见项被抽走 / 滚动跳动。
      var floor = -1;
      for (var i = 0; i < items.length; i++) {
        if (_mountedPostIds.contains(items[i].id)) {
          floor = i;
        }
      }

      for (var i = 0; i < items.length; i++) {
        if (!_matchesRemoval(patch, items[i])) {
          continue;
        }
        if (floor >= 0 && i > floor) {
          removableIds.add(items[i].id);
        } else {
          // 无任何已挂载项（floor < 0，feed 不在前台/视口未知）或位于视口内/之上 → 暂缓。
          deferredCount++;
        }
      }
    }

    if (removableIds.isNotEmpty) {
      final notifier = ref.read(discoveryFeedMapProvider.notifier);
      for (final id in removableIds) {
        notifier.removePostLocally(id);
      }
    }

    _recordEvent(
      'feed_patch_removal_applied',
      patch,
      channels: targetChannels,
      appliedCount: removableIds.length,
      deferredCount: deferredCount,
    );
  }

  bool _matchesRemoval(FeedRealtimePatch patch, ContentPostViewData item) {
    // 显式命中的单条内容（post 维度由 targetPostIds 承载）。
    if (patch.targetPostIds.contains(item.id)) {
      return true;
    }
    final dimension = patch.removalDimension;
    final value = patch.removalDimensionValue?.trim() ?? '';
    if (dimension == null || value.isEmpty) {
      return false;
    }
    switch (dimension) {
      case FeedPatchRemovalDimension.post:
        return false;
      case FeedPatchRemovalDimension.author:
        return item.authorId == value || item.personaId == value;
      case FeedPatchRemovalDimension.contentType:
        return item.identity == value ||
            item.type == value ||
            item.displayFormat == value;
    }
  }

  // ── 内部：提示合并（不插入、不跳位）────────────────────────────────────────

  void _applyHint(
    FeedRealtimePatch patch,
    List<String> targetChannels, {
    int candidateDelta = 0,
    bool refresh = false,
  }) {
    final updated = Map<String, FeedRealtimePatchHint>.from(state.hints);
    for (final channelKey in targetChannels) {
      final existing =
          updated[channelKey] ??
          FeedRealtimePatchHint(
            channelId: channelKey,
            reasonCode: patch.reasonCode,
          );
      updated[channelKey] = existing.copyWith(
        newCandidateCount: candidateDelta > 0
            ? existing.newCandidateCount + candidateDelta
            : existing.newCandidateCount,
        refreshSuggested: refresh ? true : existing.refreshSuggested,
        reasonCode: patch.reasonCode,
        lastPatchId: patch.patchId,
        feedRequestId: patch.feedRequestId ?? existing.feedRequestId,
        policyDigest: patch.policyDigest,
      );
    }
    state = FeedRealtimePatchState(hints: updated);
    _recordEvent('feed_patch_displayed', patch, channels: targetChannels);
  }

  void _clearHint(String channelId) {
    if (!state.hints.containsKey(channelId)) {
      return;
    }
    final updated = Map<String, FeedRealtimePatchHint>.from(state.hints)
      ..remove(channelId);
    state = FeedRealtimePatchState(hints: updated);
  }

  // ── 内部：去重窗口 ─────────────────────────────────────────────────────────

  void _markPatchApplied(String patchId) {
    _appliedPatchIds.add(patchId);
    while (_appliedPatchIds.length > _maxTrackedPatchIds) {
      _appliedPatchIds.remove(_appliedPatchIds.first);
    }
  }

  // ── 内部：鉴权 ─────────────────────────────────────────────────────────────

  String _currentUserId() {
    final auth = ref.read(authSessionControllerProvider);
    if (!auth.isAuthenticated) {
      return '';
    }
    final personaId = auth.activePersonaId.trim();
    if (personaId.isNotEmpty) {
      return personaId;
    }
    return auth.ownerId.trim();
  }

  // ── 内部：反馈回流（统一埋点出口，不新开第二套）───────────────────────────

  void _recordEvent(
    String eventName,
    FeedRealtimePatch patch, {
    List<String> channels = const <String>[],
    int? appliedCount,
    int? deferredCount,
  }) {
    _emit(eventName, <String, dynamic>{
      'patchId': patch.patchId,
      'patchType': patch.patchType.wire,
      'reasonCode': patch.reasonCode.wire,
      'feedRequestId': patch.feedRequestId ?? '',
      'channelId': patch.channelId ?? '',
      'affectedCount': patch.affectedCount,
      'safeToApplyWhileViewing': patch.safeToApplyWhileViewing,
      'targetChannels': channels.join(','),
      if (patch.policyDigest != null) 'policyDigest': patch.policyDigest,
      if (patch.removalDimension != null)
        'removalDimension': patch.removalDimension!.wire,
      'appliedCount': ?appliedCount,
      'deferredCount': ?deferredCount,
    });
  }

  void _recordHintEvent(
    String eventName,
    String channelId,
    FeedRealtimePatchHint hint,
  ) {
    _emit(eventName, <String, dynamic>{
      'patchId': hint.lastPatchId,
      'reasonCode': hint.reasonCode.wire,
      'feedRequestId': hint.feedRequestId ?? '',
      'channelId': channelId,
      'newCandidateCount': hint.newCandidateCount,
      'refreshSuggested': hint.refreshSuggested,
      if (hint.policyDigest != null) 'policyDigest': hint.policyDigest,
    });
  }

  void _emit(String eventName, Map<String, Object?> properties) {
    unawaited(
      ref
          .read(analyticsProvider)
          .trackEvent(
            AnalyticsEvent(
              eventType: 'feed_realtime_patch',
              eventName: eventName,
              properties: properties,
            ),
          ),
    );
  }
}

/// 实时 patch 安全消费者（UI 唯一入口；realtime 层路由至此）。
final feedRealtimePatchProvider =
    NotifierProvider<FeedRealtimePatchNotifier, FeedRealtimePatchState>(
      FeedRealtimePatchNotifier.new,
    );

/// 按 channelId 读取实时 patch 提示态（顶部更新 pill 消费）。
final feedRealtimePatchHintProvider =
    Provider.family<FeedRealtimePatchHint?, String>((ref, channelId) {
      return ref.watch(feedRealtimePatchProvider).hintFor(channelId);
    });
