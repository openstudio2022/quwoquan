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

bool _validAction(AssistantActionIntentWire action) =>
    isValidAssistantActionIntent(action);

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
