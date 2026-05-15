import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

const _uuid = Uuid();
const _sessionTimeoutMinutes = 30;

class _FeedSessionState {
  _FeedSessionState()
      : sessionId = _uuid.v4(),
        _lastActivity = DateTime.now();

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

  String newFeedRequestId() => _uuid.v4();

  void invalidate() {
    _state = _FeedSessionState();
    state = _state.sessionId;
  }
}

final feedSessionProvider =
    NotifierProvider<FeedSessionNotifier, String>(FeedSessionNotifier.new);
