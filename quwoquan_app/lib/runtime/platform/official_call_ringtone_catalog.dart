/// 官方来电铃声目录：铃声 id（`official.*` 命名空间，与 user_settings 契约同源）
/// 到平台呈现资源路径的唯一映射。
///
/// 本目录是设置页可选项与 CallKit 呈现资源的单一真相源；设置页禁止另造 ID。
/// v1 策略：官方铃声尚未提供差异化音频资产，全部条目映射系统默认铃；
/// 引入真实音频资产时只需更新本目录的 callkitPath，选项与持久化 ID 不变。
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
