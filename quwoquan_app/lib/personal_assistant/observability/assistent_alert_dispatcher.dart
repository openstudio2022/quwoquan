import 'package:quwoquan_app/personal_assistant/observability/assistent_slo_monitor.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class AssistentAlertDispatcher {
  AssistentAlertDispatcher({
    String? webhookUrl,
    String? feishuBotWebhook,
    int? suppressWindowSeconds,
    bool? logChannelEnabled,
  })  : _webhookUrl = webhookUrl ?? const String.fromEnvironment('ASSISTENT_ALERT_WEBHOOK_URL'),
        _feishuBotWebhook =
            feishuBotWebhook ?? const String.fromEnvironment('ASSISTENT_ALERT_FEISHU_WEBHOOK'),
        _suppressWindowSeconds = suppressWindowSeconds ??
            const int.fromEnvironment('ASSISTENT_ALERT_SUPPRESS_SECONDS', defaultValue: 180),
        _logChannelEnabled = logChannelEnabled ?? true;

  final List<AssistentSloAlert> _alerts = <AssistentSloAlert>[];
  final Map<String, DateTime> _lastDispatchAt = <String, DateTime>{};
  final String _webhookUrl;
  final String _feishuBotWebhook;
  final int _suppressWindowSeconds;
  final bool _logChannelEnabled;

  Map<String, dynamic> routingConfig() {
    return <String, dynamic>{
      'logEnabled': _logChannelEnabled,
      'webhookEnabled': _webhookUrl.trim().isNotEmpty,
      'feishuWebhookEnabled': _feishuBotWebhook.trim().isNotEmpty,
      'suppressWindowSeconds': _suppressWindowSeconds,
    };
  }

  Future<void> dispatch(AssistentSloAlert alert) async {
    final key = '${alert.providerId}:${alert.severity.name}';
    final now = DateTime.now();
    final last = _lastDispatchAt[key];
    if (last != null &&
        now.difference(last).inSeconds < _suppressWindowSeconds) {
      return;
    }
    _lastDispatchAt[key] = now;
    _alerts.add(alert);
    if (_alerts.length > 2000) {
      _alerts.removeRange(0, _alerts.length - 2000);
    }
    if (_logChannelEnabled) {
      // ignore: avoid_print
      print('[assistent_alert] ${jsonEncode(alert.toJson())}');
    }
    await _dispatchWebhook(alert);
    await _dispatchFeishu(alert);
  }

  List<AssistentSloAlert> listRecent({int limit = 50}) {
    if (_alerts.length <= limit) {
      return List<AssistentSloAlert>.from(_alerts.reversed);
    }
    final start = _alerts.length - limit;
    return _alerts.sublist(start).reversed.toList(growable: false);
  }

  Future<AssistentSloAlert> dispatchSynthetic({
    required String providerId,
    required AssistentSloAlertSeverity severity,
    required String message,
  }) async {
    final alert = AssistentSloAlert(
      providerId: providerId,
      severity: severity,
      message: message,
      snapshot: const AssistentSloSnapshot(
        windowMinutes: 5,
        p95LatencyMs: 9999,
        availability: 0.7,
        errorRate: 0.3,
      ),
      timestamp: DateTime.now(),
    );
    await dispatch(alert);
    return alert;
  }

  Future<void> _dispatchWebhook(AssistentSloAlert alert) async {
    if (_webhookUrl.trim().isEmpty) return;
    try {
      await http.post(
        Uri.parse(_webhookUrl),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'source': 'assistent_v1',
          'alert': alert.toJson(),
        }),
      );
    } catch (_) {
      // noop
    }
  }

  Future<void> _dispatchFeishu(AssistentSloAlert alert) async {
    if (_feishuBotWebhook.trim().isEmpty) return;
    final text =
        'Assistent SLO Alert\\nprovider=${alert.providerId}\\nseverity=${alert.severity.name}\\nmessage=${alert.message}';
    try {
      await http.post(
        Uri.parse(_feishuBotWebhook),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'msg_type': 'text',
          'content': <String, dynamic>{
            'text': text,
          },
        }),
      );
    } catch (_) {
      // noop
    }
  }
}

