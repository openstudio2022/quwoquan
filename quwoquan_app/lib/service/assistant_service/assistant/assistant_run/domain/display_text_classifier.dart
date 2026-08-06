import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/progress_text_policy.dart';

class DisplayTextClassifier {
  DisplayTextClassifier._();

  static final DisplayTextClassifier instance = DisplayTextClassifier._();
  static const String _policyPath =
      'assets/assistant/config/progress_text_policy.json';

  ProgressTextPolicy _policy = ProgressTextPolicy.defaults;
  Future<void>? _loading;
  bool _loaded = false;

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    _loading ??= _load();
    await _loading;
  }

  Future<void> _load() async {
    try {
      final decoded = jsonDecode(await rootBundle.loadString(_policyPath));
      if (decoded is Map) {
        _policy = ProgressTextPolicy.fromJson(decoded.cast<String, dynamic>());
      }
    } catch (_) {
      _policy = ProgressTextPolicy.defaults;
    }
    _loaded = true;
  }

  bool isJsonEnvelopeLike(String value) {
    final t = value.trim();
    if (!t.startsWith('{') && !t.startsWith('[') && !t.startsWith('```')) {
      return false;
    }
    for (final signature in _policy.jsonEnvelopeSignatures) {
      if (signature.isNotEmpty && t.contains(signature)) return true;
    }
    return false;
  }

  bool isDegradedText(String value) {
    final t = value.trim();
    if (t.isEmpty) return false;
    return false;
  }

  bool isProgressPlaceholder(String value) {
    final t = value.trim();
    if (t.isEmpty) return false;
    return false;
  }
}
