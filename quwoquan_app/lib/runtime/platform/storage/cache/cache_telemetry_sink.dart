import 'dart:developer' as developer;

/// Lightweight cache telemetry boundary.
///
/// Cache services depend on this interface instead of a concrete app log
/// pipeline, so tests and platform-specific assembly can inject the right sink.
abstract class CacheTelemetrySink {
  void record(String eventName, Map<String, Object?> attributes);
}

class DeveloperLogCacheTelemetrySink implements CacheTelemetrySink {
  const DeveloperLogCacheTelemetrySink({this.name = 'ContentCache'});

  final String name;

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    developer.log(eventName, name: name, error: attributes);
  }
}

class NoopCacheTelemetrySink implements CacheTelemetrySink {
  const NoopCacheTelemetrySink();

  @override
  void record(String eventName, Map<String, Object?> attributes) {}
}
