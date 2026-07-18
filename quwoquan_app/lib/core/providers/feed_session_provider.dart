import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

const _uuid = Uuid();
const _sessionTimeoutMinutes = 30;

class _FeedSessionState {
  _FeedSessionState() : sessionId = _uuid.v4(), _lastActivity = DateTime.now();

  final String sessionId;
  DateTime _lastActivity;

  bool get isExpired =>
      DateTime.now().difference(_lastActivity).inMinutes >=
      _sessionTimeoutMinutes;

  void touch() {
    _lastActivity = DateTime.now();
  }
}

class FeedSessionNotifier extends Notifier<String> {
  _FeedSessionState _state = _FeedSessionState();
  String _currentFeedRequestId = _uuid.v4();
  String _currentRankingVersion = '';
  String _currentReasonVersion = '';

  @override
  String build() {
    return _state.sessionId;
  }

  String get sessionId {
    if (_state.isExpired) {
      _state = _FeedSessionState();
      state = _state.sessionId;
    } else {
      _state.touch();
    }
    return _state.sessionId;
  }

  /// 当前 feed 会话的 feedRequestId。
  ///
  /// 首页发现流为服务端权威下发（见 [adoptServerFeedRequestId]）；尚未接入服务端
  /// feed envelope 的其他面（搜索/圈子/个人作品等）暂由 [newFeedRequestId] 客户端生成。
  String get currentFeedRequestId => _currentFeedRequestId;

  /// 当前 feed 会话归因的精排管线版本（服务端 envelope.rankingVersion）；
  /// 尚未接入服务端 feed envelope 的面（搜索/圈子/个人作品等）为空字符串。
  String get currentRankingVersion => _currentRankingVersion;

  /// 当前 feed 会话归因的理由生成版本（服务端 envelope.reasonVersion）。
  String get currentReasonVersion => _currentReasonVersion;

  /// 采纳服务端 GET /content/feed 下发的权威 feedRequestId。
  ///
  /// 首页发现流加载/分页后调用，使 [currentFeedRequestId] 与服务端 envelope 对齐，
  /// 后续曝光/点击/打开等行为事件复用同一归因 id。空值忽略（保留上一个有效 id）。
  /// 同步采纳 envelope.rankingVersion（非空才覆盖），使行为事件可按精排版本归因。
  void adoptServerFeedRequestId(
    String? feedRequestId, {
    String? rankingVersion,
    String? reasonVersion,
  }) {
    final normalized = feedRequestId?.trim() ?? '';
    if (normalized.isEmpty) {
      return;
    }
    _currentFeedRequestId = normalized;
    final normalizedRanking = rankingVersion?.trim() ?? '';
    if (normalizedRanking.isNotEmpty) {
      _currentRankingVersion = normalizedRanking;
    }
    final normalizedReason = reasonVersion?.trim() ?? '';
    if (normalizedReason.isNotEmpty) {
      _currentReasonVersion = normalizedReason;
    }
  }

  String newFeedRequestId() {
    _currentFeedRequestId = _uuid.v4();
    return _currentFeedRequestId;
  }

  void invalidate() {
    _state = _FeedSessionState();
    state = _state.sessionId;
  }
}

final feedSessionProvider = NotifierProvider<FeedSessionNotifier, String>(
  FeedSessionNotifier.new,
);
