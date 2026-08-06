/// 官方来电铃声目录：铃声 id（`official.*` 命名空间，与 user_settings 契约同源）
/// 到平台呈现资源路径的唯一映射。
library;

final class OfficialCallRingtone {
  const OfficialCallRingtone({
    required this.id,
    required this.label,
    required this.callkitPath,
  });

  final String id;
  final String label;
  final String callkitPath;
}

abstract final class OfficialCallRingtoneCatalog {
  static const String defaultId = 'official.default';

  static const List<OfficialCallRingtone> items = <OfficialCallRingtone>[
    OfficialCallRingtone(
      id: defaultId,
      label: '趣聊默认',
      callkitPath: 'system_ringtone_default',
    ),
    OfficialCallRingtone(
      id: 'official.blue-wave',
      label: '蓝色回响',
      callkitPath: 'system_ringtone_default',
    ),
    OfficialCallRingtone(
      id: 'official.morning-light',
      label: '清晨微光',
      callkitPath: 'system_ringtone_default',
    ),
  ];

  static bool contains(String? id) {
    if (id == null || id.isEmpty) return false;
    return items.any((item) => item.id == id);
  }

  static String resolveCallkitPath(String? id) {
    final ringtone = items.where((item) => item.id == id).firstOrNull;
    return ringtone?.callkitPath ?? 'system_ringtone_default';
  }
}
