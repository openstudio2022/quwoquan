import 'package:quwoquan_app/runtime/platform/temporary_file_cleanup_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/runtime/platform/temporary_file_cleanup_web.dart';

/// 仅删除 App 临时目录内的文件；越界路径必须 fail-closed。
Future<void> deleteAppTemporaryFile(String path) =>
    deletePlatformTemporaryFile(path);

/// 账号 closed 终态专用：清空 App 沙箱临时目录中的全部可重建文件。
Future<void> clearAppTemporaryDirectoryForTerminalAccountClosure() =>
    clearPlatformTemporaryDirectoryForTerminalAccountClosure();
