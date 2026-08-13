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

/// 静默丢弃缓存遥测的 null-object 实现。
///
/// 用于不需要缓存观测的装配点（如一次性 probe store）；不是测试替身。
class SilentCacheTelemetrySink implements CacheTelemetrySink {
  const SilentCacheTelemetrySink();

  @override
  void record(String eventName, Map<String, Object?> attributes) {}
}
