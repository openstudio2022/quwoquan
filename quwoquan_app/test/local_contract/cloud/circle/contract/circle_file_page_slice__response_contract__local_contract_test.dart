import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('CircleFilePageSlice response contract', () {
    test('decodes paged items and preserves the next cursor', () {
      final page = decodeCircleFilePageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'fileId': 'file-1',
            'version': 1,
            'circleId': 'circle-1',
            'groupId': null,
            'parentFolderId': null,
            'name': 'guide.png',
            'fileType': 'file',
            'assetId': 'asset-1',
            'mimeType': 'image/png',
            'sizeBytes': 4096,
            'uploaderPersonaId': 'persona-1',
            'status': 'active',
            'createdAt': '2026-07-15T00:00:00Z',
            'updatedAt': '2026-07-15T00:01:00Z',
          },
        ],
        'cursor': 'next-page',
      });

      expect(page.items, hasLength(1));
      expect(page.items.single.fileId, 'file-1');
      expect(page.items.single.name, 'guide.png');
      expect(page.nextCursor, 'next-page');
    });

    test('uses only circle id as a path parameter for list queries', () {
      final payload = encodeCircleCircleFileListCircleFilesGeneratedRequest(
        CircleFileListQuery(
          circleId: 'circle-1',
          groupId: 'group-1',
          parentFolderId: 'folder-1',
          cursor: 'next-page',
          limit: 50,
        ),
      );

      expect(payload.pathParameters, <String, String>{'circleId': 'circle-1'});
      expect(payload.queryParameters, <String, String>{
        'groupId': 'group-1',
        'parentFolderId': 'folder-1',
        'cursor': 'next-page',
        'limit': '50',
      });
    });

    test(
      'rejects unknown response fields instead of silently accepting drift',
      () {
        expect(
          () => decodeCircleFilePageSlice(<String, Object?>{
            'items': const <Object?>[],
            'cursor': null,
            'unexpectedField': 'must-not-be-accepted',
          }),
          throwsFormatException,
        );
      },
    );
  });
}
