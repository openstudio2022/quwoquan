import 'package:file_picker/file_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/desktop_picker_ports.dart';

class FilePickerDesktopDirectoryPicker implements DesktopDirectoryPicker {
  const FilePickerDesktopDirectoryPicker();

  @override
  Future<String?> pickDirectory({String? initialDirectory}) {
    return FilePicker.getDirectoryPath(
      initialDirectory: initialDirectory,
      windowsOptions: const WindowsOptions(lockParentWindow: true),
      linuxOptions: const LinuxOptions(lockParentWindow: true),
    );
  }
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

  @override
  Future<void> clearForTerminalAccountClosure() async {
    final preferences = await _prefsFactory();
    await preferences.remove(_key);
    if (preferences.containsKey(_key)) {
      throw StateError('desktop picker directory cleanup verification failed');
    }
  }
}
