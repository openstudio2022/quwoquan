import 'package:uuid/uuid.dart';

/// Cross-object attribution identity for one active feed browsing session.
///
/// The value object lives with runtime shell state; `runtime/di` only binds it
/// to Riverpod and must not own the mutable session model.
class FeedAttributionSession {
  FeedAttributionSession({required Uuid uuid, required DateTime now})
    : sessionId = uuid.v4(),
      _lastActivity = now;

  final String sessionId;
  DateTime _lastActivity;

  bool isExpired(DateTime now, {required Duration timeout}) =>
      now.difference(_lastActivity) >= timeout;

  void touch(DateTime now) {
    _lastActivity = now;
  }
}
