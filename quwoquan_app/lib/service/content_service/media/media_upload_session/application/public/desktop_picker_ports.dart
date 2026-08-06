import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';

/// Pure capability policy for choosing the desktop image picker.
bool shouldUseDesktopImagePicker({
  required bool hasMediaLibrary,
  required bool hasLocalFileSystem,
  required MediaPickerEntryMode mode,
}) {
  return mode == MediaPickerEntryMode.image &&
      !hasMediaLibrary &&
      hasLocalFileSystem;
}

/// Application port for the host directory picker.
abstract interface class DesktopDirectoryPicker {
  Future<String?> pickDirectory({String? initialDirectory});
}

/// Application port for the last desktop media directory.
abstract interface class DesktopPickerDirectoryMemory {
  Future<String?> lastDirectory();

  Future<void> rememberDirectory(String path);

  Future<void> clearForTerminalAccountClosure();
}
