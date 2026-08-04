import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';

/// 桌面（本机文件系统）下的一个图片相册：某个目录直接包含的图片集合。
class DesktopImageAlbum {
  const DesktopImageAlbum({
    required this.id,
    required this.directoryPath,
    required this.name,
    required this.imagePaths,
    this.isAll = false,
  });

  /// 稳定标识：目录路径（合成「全部照片」相册用固定 id）。
  final String id;
  final String directoryPath;
  final String name;
  final List<String> imagePaths;

  /// 是否为跨目录聚合的「全部照片」相册（与移动端 isAll 语义对齐，置顶展示）。
  final bool isAll;

  int get count => imagePaths.length;
}

/// 递归扫描一个根目录，把「直接包含图片的子目录」聚合为相册。
///
/// 设计（对齐 `.cursor/rules/14-cross-platform-portability` 能力优先 + R-XP3 dart:io 收口）：
/// - 仅通过 [FileStorageGateway.listDirectory] 单层枚举，自身控制递归与上限，
///   既便于纯单测注入，也便于对桌面大目录做性能管控（深度 / 目录数 / 单册图片数封顶）。
/// - 产出按「全部照片」(isAll，跨目录聚合) 置顶，其余目录按图片数降序、名称升序。
class DesktopImageAlbumScanner {
  const DesktopImageAlbumScanner({
    this.maxDirectories = 600,
    this.maxDepth = 6,
    this.maxImagesPerAlbum = 2000,
    this.allAlbumName = '全部照片',
  });

  /// 最多遍历的目录数（含根），超出后停止下探，保护超大目录树。
  final int maxDirectories;

  /// 最大递归深度（根为 0）。
  final int maxDepth;

  /// 单个相册（含聚合册）最多保留的图片数。
  final int maxImagesPerAlbum;

  /// 跨目录聚合相册的显示名。
  final String allAlbumName;

  static const Set<String> imageExtensions = <String>{
    '.jpg',
    '.jpeg',
    '.png',
    '.gif',
    '.webp',
    '.bmp',
    '.heic',
    '.heif',
  };

  Future<List<DesktopImageAlbum>> scan(
    FileStorageGateway gateway,
    String rootPath,
  ) async {
    if (!gateway.isSupported) {
      return const <DesktopImageAlbum>[];
    }
    final perDirectory = <DesktopImageAlbum>[];
    final aggregated = <String>[];
    var visited = 0;

    // 显式栈，避免递归调用栈过深；按 (path, depth) 下探。
    final stack = <_PendingDir>[_PendingDir(rootPath, 0)];
    while (stack.isNotEmpty && visited < maxDirectories) {
      final current = stack.removeLast();
      visited++;
      final entries = await gateway.listDirectory(current.path);
      final images = <String>[];
      for (final entry in entries) {
        if (entry.isDirectory) {
          if (current.depth < maxDepth) {
            stack.add(_PendingDir(entry.path, current.depth + 1));
          }
        } else if (_isImagePath(entry.path)) {
          images.add(entry.path);
        }
      }
      if (images.isEmpty) {
        continue;
      }
      images.sort();
      final capped = images.length > maxImagesPerAlbum
          ? images.sublist(0, maxImagesPerAlbum)
          : images;
      perDirectory.add(
        DesktopImageAlbum(
          id: current.path,
          directoryPath: current.path,
          name: _basename(current.path),
          imagePaths: capped,
        ),
      );
      for (final image in capped) {
        if (aggregated.length >= maxImagesPerAlbum) {
          break;
        }
        aggregated.add(image);
      }
    }

    perDirectory.sort((a, b) {
      final countCompare = b.count.compareTo(a.count);
      if (countCompare != 0) return countCompare;
      return a.name.compareTo(b.name);
    });

    final albums = <DesktopImageAlbum>[];
    if (aggregated.isNotEmpty) {
      albums.add(
        DesktopImageAlbum(
          id: '__all__',
          directoryPath: rootPath,
          name: allAlbumName,
          imagePaths: aggregated,
          isAll: true,
        ),
      );
    }
    albums.addAll(perDirectory);
    return albums;
  }

  bool _isImagePath(String path) {
    final dot = path.lastIndexOf('.');
    if (dot < 0) return false;
    final ext = path.substring(dot).toLowerCase();
    return imageExtensions.contains(ext);
  }

  String _basename(String path) {
    var trimmed = path;
    while (trimmed.length > 1 &&
        (trimmed.endsWith('/') || trimmed.endsWith('\\'))) {
      trimmed = trimmed.substring(0, trimmed.length - 1);
    }
    final slash = trimmed.lastIndexOf('/');
    final back = trimmed.lastIndexOf('\\');
    final cut = slash > back ? slash : back;
    final name = cut < 0 ? trimmed : trimmed.substring(cut + 1);
    return name.isEmpty ? trimmed : name;
  }
}

class _PendingDir {
  const _PendingDir(this.path, this.depth);

  final String path;
  final int depth;
}
