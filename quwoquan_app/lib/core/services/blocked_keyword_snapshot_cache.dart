import 'dart:async';

/// Feed 请求侧的短时 UserSettings.blockedKeywords 快照。
///
/// 只缓存服务端 typed Slice，不持久化第二真相源；写命令成功或账号切换立即失效。
final class BlockedKeywordSnapshotCache {
  BlockedKeywordSnapshotCache({
    this.ttl = const Duration(minutes: 5),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Duration ttl;
  final DateTime Function() _now;
  List<String> _value = const <String>[];
  DateTime? _expiresAt;
  Future<List<String>>? _inflight;

  Future<List<String>> load(Future<List<String>> Function() loader) {
    final expiresAt = _expiresAt;
    if (expiresAt != null && _now().isBefore(expiresAt)) {
      return Future<List<String>>.value(_value);
    }
    final inflight = _inflight;
    if (inflight != null) return inflight;
    final request = loader()
        .then((items) {
          replace(items);
          return _value;
        })
        .whenComplete(() => _inflight = null);
    _inflight = request;
    return request;
  }

  void replace(Iterable<String> items) {
    _value = List<String>.unmodifiable(
      items.map((item) => item.trim()).where((item) => item.isNotEmpty).toSet(),
    );
    _expiresAt = _now().add(ttl);
  }

  void clear() {
    _value = const <String>[];
    _expiresAt = null;
    _inflight = null;
  }
}
