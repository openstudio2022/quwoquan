import 'dart:math';

class AppTraceContextStore {
  AppTraceContextStore._();

  static final AppTraceContextStore instance = AppTraceContextStore._();
  final Random _random = Random();

  String? _sessionId;
  String? _journeyId;

  String get sessionId => _sessionId ??= _newId('sess');
  String get journeyId => _journeyId ??= _newId('journey');

  void renewJourney() {
    _journeyId = _newId('journey');
  }

  String newPageVisitId() => _newId('visit');
  String newSpanId() => _newId('span');
  String newRequestId() => _newId('req');

  String _newId(String prefix) {
    final ts = DateTime.now().millisecondsSinceEpoch;
    final r = _random.nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
    return '${prefix}_$ts$r';
  }
}
