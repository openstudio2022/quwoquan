import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('我的举报 pure contract', () {
    test('查询编码携带稳定 cursor 与 limit', () {
      final payload = encodeContentMyReportsQuery(
        const ContentMyReportsQuery(cursor: 'cursor-1', limit: 10),
      );

      expect(payload.queryParameters, <String, String>{
        'cursor': 'cursor-1',
        'limit': '10',
      });
    });

    test('严格解码举报生命周期且不需要运营字段', () {
      final page = decodeContentMyReportPage(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'id': 'report-1',
            'targetType': 'post',
            'targetId': 'post-1',
            'reason': 'spam',
            'description': '重复广告',
            'status': 'resolved',
            'createdAt': '2026-07-20T00:00:00Z',
            'updatedAt': '2026-07-20T01:00:00Z',
            'resolvedAt': '2026-07-20T01:00:00Z',
          },
        ],
        'nextCursor': 'cursor-2',
      });

      expect(page.items, hasLength(1));
      expect(page.items.single.targetType, ContentReportTargetType.post);
      expect(page.items.single.reason, ContentReportReason.spam);
      expect(page.items.single.status, ContentReportStatus.resolved);
      expect(page.nextCursor, 'cursor-2');
    });

    test('未知状态 fail closed', () {
      expect(
        () => decodeContentMyReportPage(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'id': 'report-1',
              'targetType': 'post',
              'targetId': 'post-1',
              'reason': 'spam',
              'status': 'unknown',
              'createdAt': '2026-07-20T00:00:00Z',
              'updatedAt': '2026-07-20T00:00:00Z',
            },
          ],
        }),
        throwsFormatException,
      );
    });
  });
}
