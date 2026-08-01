// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — typed action payload 允许受限扩展键并递归拒绝危险键。
part of 'assistant_presentation_renderer.dart';

bool _validStyle(AssistantPresentationStyleWire style) =>
    const {'normal', 'subtle', 'strong'}.contains(style.emphasis) &&
    const {'standard', 'outlined', 'filled', 'hero'}.contains(style.variant) &&
    const {
      'start',
      'center',
      'end',
      'space_between',
    }.contains(style.alignment) &&
    const {
      'none',
      'related',
      'section',
      'screen',
    }.contains(style.spacingRole) &&
    style.aspectRatio >= 0 &&
    style.aspectRatio <= 10 &&
    style.responsiveSpan >= 1 &&
    style.responsiveSpan <= 12;

bool _validAction(AssistantActionIntentWire action) {
  if (action.intentId.isEmpty || action.operation.isEmpty) return false;
  return !_containsUnsafeActionKey(action.payload);
}

bool _containsUnsafeActionKey(Map<String, dynamic> payload) {
  for (final entry in payload.entries) {
    final key = entry.key.toLowerCase().replaceAll('_', '');
    if (const {
      'url',
      'route',
      'callback',
      'callbackurl',
      'javascript',
      'script',
      'authorization',
      'cookie',
    }.contains(key)) {
      return true;
    }
    final value = entry.value;
    if (value is Map &&
        _containsUnsafeActionKey(value.cast<String, dynamic>())) {
      return true;
    }
  }
  return false;
}

List<String> _stringList(Object? value) => value is List
    ? value
          .whereType<String>()
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .take(16)
          .toList(growable: false)
    : const [];

List<Map<String, dynamic>> _mapList(Object? value) => value is List
    ? value
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .take(64)
          .toList(growable: false)
    : const [];

IconData _iconData(String token) => switch (token) {
  'calendar' => CupertinoIcons.calendar,
  'clock' => CupertinoIcons.clock,
  'location' => CupertinoIcons.location,
  'weather' => CupertinoIcons.cloud_sun,
  'warning' => CupertinoIcons.exclamationmark_triangle,
  'check' => CupertinoIcons.check_mark_circled,
  'info' => CupertinoIcons.info_circle,
  'travel' => CupertinoIcons.airplane,
  'source' => CupertinoIcons.link,
  'image' => CupertinoIcons.photo,
  _ => CupertinoIcons.sparkles,
};

final RegExp _digestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
