import 'package:flutter_riverpod/flutter_riverpod.dart';

class AnalyticsEvent {
  final String eventType;
  final String eventName;
  final Map<String, dynamic> properties;
  
  const AnalyticsEvent({
    required this.eventType,
    required this.eventName,
    this.properties = const {},
  });
}

class AnalyticsConfig {
  final bool enabled;
  
  const AnalyticsConfig({this.enabled = true});
}

class AnalyticsService {
  Future<void> initialize(AnalyticsConfig config) async {
    // Stub implementation
  }
  
  Future<void> trackEvent(AnalyticsEvent event) async {
    // Stub implementation
  }
}

final analyticsConfigProvider = Provider<AnalyticsConfig>((ref) {
  return const AnalyticsConfig();
});

final analyticsProvider = Provider<AnalyticsService>((ref) {
  return AnalyticsService();
});

