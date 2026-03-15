import 'dart:io';

class AppPerfProbe {
  const AppPerfProbe();

  static Map<String, dynamic> snapshot({
    required String event,
    required String route,
    String operation = '',
    int? latencyMs,
  }) {
    final rssBytes = ProcessInfo.currentRss;
    return <String, dynamic>{
      'event': event,
      'route': route,
      if (operation.isNotEmpty) 'operation': operation,
      'memory': <String, dynamic>{'rssMb': _bytesToMb(rssBytes)},
      'cpu': <String, dynamic>{'processUsagePercent': null},
      'latencyMs': latencyMs,
    };
  }

  static double _bytesToMb(int bytes) {
    if (bytes <= 0) return 0.0;
    return bytes / (1024 * 1024);
  }
}
