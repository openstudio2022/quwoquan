import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';

/// 图片选择是否应走桌面（本机文件系统扫描）选择器。
///
/// 唯一判据是能力位而非平台名（对齐 `.cursor/rules/14-cross-platform-portability`
/// R-XP1 能力优先）：仅当「无系统相册（mediaLibrary == false）但有本机文件系统
/// （hasLocalFileSystem）」且为图片入口时返回 true。其余（移动 / web 的系统相册、
/// 视频入口）走系统相册选择器。创作页与单测共用此函数，杜绝路由判据双真相源。
bool shouldUseDesktopImagePicker(
  PlatformCapabilities capabilities,
  MediaPickerEntryMode mode,
) {
  return mode == MediaPickerEntryMode.image &&
      !capabilities.mediaLibrary &&
      capabilities.hasLocalFileSystem;
}

/// 桌面「选择文件夹」能力的防腐抽象。
///
/// 包装 `file_picker` 的目录选择对话框；抽象出来便于在 widget 测试里注入假实现，
/// 不触碰平台通道（对齐 `.cursor/rules/14-cross-platform-portability` 原生能力走接口）。
abstract class DesktopDirectoryPicker {
  /// 弹出系统目录选择框。[initialDirectory] 为上次记忆目录（可空）。
  /// 用户取消返回 null。
  Future<String?> pickDirectory({String? initialDirectory});
}

class FilePickerDesktopDirectoryPicker implements DesktopDirectoryPicker {
  const FilePickerDesktopDirectoryPicker();

  @override
  Future<String?> pickDirectory({String? initialDirectory}) {
    return FilePicker.getDirectoryPath(
      initialDirectory: initialDirectory,
      lockParentWindow: true,
    );
  }
}

final desktopDirectoryPickerProvider = Provider<DesktopDirectoryPicker>(
  (ref) => const FilePickerDesktopDirectoryPicker(),
);

/// 记忆「上次打开的图片目录」。
abstract class DesktopPickerDirectoryMemory {
  Future<String?> lastDirectory();

  Future<void> rememberDirectory(String path);
}

class PrefsDesktopPickerDirectoryMemory
    implements DesktopPickerDirectoryMemory {
  PrefsDesktopPickerDirectoryMemory({
    Future<SharedPreferences> Function()? prefsFactory,
  }) : _prefsFactory = prefsFactory ?? SharedPreferences.getInstance;

  static const String _key = 'desktop_image_picker_last_directory';

  final Future<SharedPreferences> Function() _prefsFactory;

  @override
  Future<String?> lastDirectory() async {
    final prefs = await _prefsFactory();
    final value = prefs.getString(_key);
    if (value == null || value.isEmpty) {
      return null;
    }
    return value;
  }

  @override
  Future<void> rememberDirectory(String path) async {
    if (path.isEmpty) return;
    final prefs = await _prefsFactory();
    await prefs.setString(_key, path);
  }

  Future<void> clearForTerminalAccountClosure() async {
    final preferences = await _prefsFactory();
    await preferences.remove(_key);
    if (preferences.containsKey(_key)) {
      throw StateError('desktop picker directory cleanup verification failed');
    }
  }
}

final desktopPickerDirectoryMemoryProvider =
    Provider<DesktopPickerDirectoryMemory>(
      (ref) => PrefsDesktopPickerDirectoryMemory(),
    );
