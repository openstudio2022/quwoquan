import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_image_album_scanner.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';

/// 内存目录树驱动的 [FileStorageGateway]，只实现 [listDirectory]，其余抛错以
/// 证明扫描器仅依赖目录枚举这一条能力。
class _InMemoryGateway implements FileStorageGateway {
  _InMemoryGateway(this._tree, {this.isSupported = true});

  /// path -> 该目录下的直接子项。
  final Map<String, List<FileSystemEntry>> _tree;

  @override
  final bool isSupported;

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      _tree[path] ?? const <FileSystemEntry>[];

  @override
  Future<String> applicationSupportPath() => throw UnimplementedError();
  @override
  Future<String> temporaryPath() => throw UnimplementedError();
  @override
  Future<bool> exists(String path) => throw UnimplementedError();
  @override
  Future<String> readAsString(String path) => throw UnimplementedError();
  @override
  Future<void> writeAsString(String path, String contents) =>
      throw UnimplementedError();
  @override
  Future<List<int>> readAsBytes(String path) => throw UnimplementedError();
  @override
  Future<void> writeAsBytes(String path, List<int> bytes) =>
      throw UnimplementedError();
  @override
  Future<void> delete(String path) => throw UnimplementedError();
  @override
  Future<void> ensureDirectory(String path) => throw UnimplementedError();
}

FileSystemEntry _dir(String path) =>
    FileSystemEntry(path: path, isDirectory: true);
FileSystemEntry _file(String path) =>
    FileSystemEntry(path: path, isDirectory: false);

void main() {
  group('DesktopImageAlbumScanner', () {
    test('递归聚合含图子目录为相册，并置顶跨目录「全部照片」', () async {
      final gateway = _InMemoryGateway(<String, List<FileSystemEntry>>{
        '/root': <FileSystemEntry>[
          _file('/root/a.jpg'),
          _file('/root/readme.txt'),
          _dir('/root/trip'),
          _dir('/root/empty'),
        ],
        '/root/trip': <FileSystemEntry>[
          _file('/root/trip/1.png'),
          _file('/root/trip/2.PNG'),
          _file('/root/trip/3.webp'),
          _dir('/root/trip/raw'),
        ],
        '/root/trip/raw': <FileSystemEntry>[
          _file('/root/trip/raw/x.heic'),
        ],
        '/root/empty': <FileSystemEntry>[
          _file('/root/empty/notes.md'),
        ],
      });

      final albums =
          await const DesktopImageAlbumScanner().scan(gateway, '/root');

      // 第一张为聚合「全部照片」，置顶且 isAll。
      expect(albums.first.isAll, isTrue);
      expect(albums.first.name, '全部照片');
      // 全部图片：root(1) + trip(3) + raw(1) = 5。
      expect(albums.first.count, 5);

      // 仅含图目录成册：root / trip / raw（empty 不成册）。
      final names = albums.skip(1).map((a) => a.name).toList();
      expect(names, containsAll(<String>['root', 'trip', 'raw']));
      expect(names.contains('empty'), isFalse);

      // 非聚合相册按图片数降序：trip(3) 在 root(1)/raw(1) 之前。
      final trip = albums.firstWhere((a) => a.name == 'trip');
      expect(trip.count, 3);
      expect(albums.indexOf(trip), 1);
    });

    test('能力位不支持时返回空列表（结构化降级，不抛错）', () async {
      final gateway = _InMemoryGateway(
        <String, List<FileSystemEntry>>{},
        isSupported: false,
      );
      final albums =
          await const DesktopImageAlbumScanner().scan(gateway, '/root');
      expect(albums, isEmpty);
    });

    test('maxDepth 限制下探深度', () async {
      final gateway = _InMemoryGateway(<String, List<FileSystemEntry>>{
        '/root': <FileSystemEntry>[_dir('/root/deep')],
        '/root/deep': <FileSystemEntry>[_file('/root/deep/a.jpg')],
      });
      // maxDepth=0：只看根，根无图 → 空。
      final albums = await const DesktopImageAlbumScanner(maxDepth: 0)
          .scan(gateway, '/root');
      expect(albums, isEmpty);
    });

    test('maxImagesPerAlbum 对单册与聚合册同时封顶', () async {
      final files = List<FileSystemEntry>.generate(
        10,
        (i) => _file('/root/img_$i.jpg'),
      );
      final gateway = _InMemoryGateway(<String, List<FileSystemEntry>>{
        '/root': files,
      });
      final albums = await const DesktopImageAlbumScanner(maxImagesPerAlbum: 4)
          .scan(gateway, '/root');
      expect(albums.first.count, 4);
      expect(albums[1].count, 4);
    });
  });
}
