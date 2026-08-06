import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/progress_text_policy.dart';

class DisplayTextClassifier {
  const DisplayTextClassifier(this._policy);

  final ProgressTextPolicy _policy;

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
