import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/media/media_candidate_failure.dart';

/// 进程级媒体加载负缓存：终端失败（尤其 4xx）在冷却期内禁止对同一 identity 再发网。
///
/// 用于阻断 Feed rebuild / 多实例并行导致的羊群效应；手动清除或冷却到期后可再试。
@immutable
class MediaLoadFailureRecord {
  const MediaLoadFailureRecord({
    required this.identity,
    required this.kind,
    required this.failedAt,
    required this.cooldown,
    this.statusCode,
  });

  final String identity;
  final MediaCandidateFailureKind kind;
  final DateTime failedAt;
  final Duration cooldown;
  final int? statusCode;

  bool isActiveAt(DateTime now) => now.isBefore(failedAt.add(cooldown));
}

class MediaLoadFailureCache {
  MediaLoadFailureCache({
    this.defaultCooldown = const Duration(seconds: 60),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  static final MediaLoadFailureCache instance = MediaLoadFailureCache();

  final Duration defaultCooldown;
  final DateTime Function() _now;
  final Map<String, MediaLoadFailureRecord> _records =
      <String, MediaLoadFailureRecord>{};
  final Set<String> _loggedIdentities = <String>{};

  @visibleForTesting
  void clear() {
    _records.clear();
    _loggedIdentities.clear();
  }

  MediaLoadFailureRecord? activeFailure(String identity) {
    final key = identity.trim();
    if (key.isEmpty) {
      return null;
    }
    final record = _records[key];
    if (record == null) {
      return null;
    }
    if (!record.isActiveAt(_now())) {
      _records.remove(key);
      return null;
    }
    return record;
  }

  bool shouldSkipNetwork(String identity) => activeFailure(identity) != null;

  void recordFailure(
    String identity, {
    required Object error,
    String? candidateUrl,
    Duration? cooldown,
  }) {
    final key = identity.trim();
    if (key.isEmpty) {
      return;
    }
    final kind = classifyMediaCandidateLoadFailure(
      error,
      candidateUrl: candidateUrl,
    );
    final statusCode = extractHttpStatusCode(error);
    final effectiveCooldown =
        cooldown ??
        (kind == MediaCandidateFailureKind.http404 ||
                kind == MediaCandidateFailureKind.http4xx
            ? defaultCooldown
            : const Duration(seconds: 15));
    _records[key] = MediaLoadFailureRecord(
      identity: key,
      kind: kind,
      failedAt: _now(),
      cooldown: effectiveCooldown,
      statusCode: statusCode,
    );
  }

  /// 仅记录不可恢复的公开媒体缺失，供视频播放器避免滚动重建造成重复请求。
  void recordTerminalFailure(
    String identity, {
    required MediaCandidateFailureKind kind,
    int? statusCode,
    Duration? cooldown,
  }) {
    if (kind != MediaCandidateFailureKind.http404 &&
        kind != MediaCandidateFailureKind.http4xx) {
      return;
    }
    final key = identity.trim();
    if (key.isEmpty) {
      return;
    }
    _records[key] = MediaLoadFailureRecord(
      identity: key,
      kind: kind,
      failedAt: _now(),
      cooldown: cooldown ?? defaultCooldown,
      statusCode: statusCode,
    );
  }

  /// 返回 true 表示本次应输出日志（同 identity 冷却窗内只打一次）。
  bool shouldLogFailure(String identity) {
    final key = identity.trim();
    if (key.isEmpty) {
      return true;
    }
    if (_loggedIdentities.contains(key)) {
      return false;
    }
    _loggedIdentities.add(key);
    return true;
  }

  void clearIdentity(String identity) {
    final key = identity.trim();
    _records.remove(key);
    _loggedIdentities.remove(key);
  }
}
