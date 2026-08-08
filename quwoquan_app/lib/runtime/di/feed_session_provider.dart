import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/state/feed_attribution_session.dart';
import 'package:uuid/uuid.dart';

// 跨对象 feed attribution session 只在 runtime/di 提供。
const _uuid = Uuid();
const _sessionTimeout = Duration(minutes: 30);

class FeedSessionNotifier extends Notifier<String> {
  FeedAttributionSession _session = _newSession();
  String _currentFeedRequestId = _uuid.v4();

  @override
  String build() {
    return _session.sessionId;
  }

  String get sessionId {
    final now = DateTime.now();
    if (_session.isExpired(now, timeout: _sessionTimeout)) {
      _session = _newSession(now);
      state = _session.sessionId;
    } else {
      _session.touch(now);
    }
    return _session.sessionId;
  }

  /// 当前 feed 会话的 feedRequestId。
  ///
  /// 首页发现流为服务端权威下发（见 [adoptServerFeedRequestId]）；尚未接入服务端
  /// feed envelope 的其他面（搜索/圈子/个人作品等）暂由 [newFeedRequestId] 客户端生成。
  String get currentFeedRequestId => _currentFeedRequestId;

  /// 采纳服务端 GET /content/feed 下发的权威 feedRequestId。
  ///
  /// 首页发现流加载/分页后调用，使 [currentFeedRequestId] 与服务端 envelope 对齐，
  /// 后续曝光/点击/打开等行为事件复用同一归因 id。空值忽略（保留上一个有效 id）。
  void adoptServerFeedRequestId(String? feedRequestId) {
    final normalized = feedRequestId?.trim() ?? '';
    if (normalized.isEmpty) {
      return;
    }
    _currentFeedRequestId = normalized;
  }

  String newFeedRequestId() {
    _currentFeedRequestId = _uuid.v4();
    return _currentFeedRequestId;
  }

  void invalidate() {
    _session = _newSession();
    state = _session.sessionId;
  }

  static FeedAttributionSession _newSession([DateTime? now]) =>
      FeedAttributionSession(uuid: _uuid, now: now ?? DateTime.now());
}

final feedSessionProvider = NotifierProvider<FeedSessionNotifier, String>(
  FeedSessionNotifier.new,
);
