import 'package:quwoquan_app/assistant/contracts/runtime_policies.dart';

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
    _policy = await ProgressTextPolicy.loadFromAsset(_policyPath);
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
    for (final prefix in _policy.degradedPrefixes) {
      if (prefix.isNotEmpty && t.startsWith(prefix)) return true;
    }
    for (final part in _policy.degradedSubstrings) {
      if (part.isNotEmpty && t.contains(part)) return true;
    }
    return false;
  }

  bool isProgressPlaceholder(String value) {
    final t = value.trim();
    if (t.isEmpty) return false;
    final hasMarkdownStructure = t.contains('\n') &&
        (t.contains('## ') ||
            t.contains('### ') ||
            t.contains('- ') ||
            t.contains('> ') ||
            t.contains('**'));
    if (hasMarkdownStructure) return false;
    final lowered = t.toLowerCase();
    for (final lexeme in _policy.progressLexicon) {
      final token = lexeme.trim();
      if (token.isEmpty) continue;
      final lowerToken = token.toLowerCase();
      if (t.contains(token) || lowered.contains(lowerToken)) return true;
    }
    return false;
  }
}
