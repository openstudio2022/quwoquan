import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/src/content/alpha_report_command.dart';
import 'package:quwoquan_cloud_mock/src/content/alpha_report_query.dart';
import 'package:test/test.dart';

void main() {
  group('AlphaContentReportAdapter', () {
    test('记录类型化举报载荷', () async {
      final adapter = AlphaContentReportAdapter();
      await adapter.createReport(
        CreateContentReportCommand(
          targetId: 'user-1',
          targetType: ContentReportTargetType.user,
          reason: ContentReportReason.spam,
        ),
      );
      expect(adapter.submitted, hasLength(1));
      expect(adapter.submitted.single.targetId, 'user-1');
      expect(adapter.submitted.single.targetType, ContentReportTargetType.user);
    });
  });

  test('Alpha 我的举报查询保持分页与状态契约', () async {
    final now = DateTime.utc(2026, 7, 20);
    final adapter = AlphaContentReportQueryAdapter(<ContentMyReportItem>[
      ContentMyReportItem(
        id: 'report-1',
        targetType: ContentReportTargetType.post,
        targetId: 'post-1',
        reason: ContentReportReason.spam,
        status: ContentReportStatus.pending,
        createdAt: now,
        updatedAt: now,
      ),
      ContentMyReportItem(
        id: 'report-2',
        targetType: ContentReportTargetType.post,
        targetId: 'post-2',
        reason: ContentReportReason.other,
        status: ContentReportStatus.resolved,
        createdAt: now,
        updatedAt: now,
      ),
    ]);

    final first = await adapter.listMyReports(
      const ContentMyReportsQuery(limit: 1),
    );
    final second = await adapter.listMyReports(
      ContentMyReportsQuery(cursor: first.nextCursor, limit: 1),
    );

    expect(first.items.single.id, 'report-1');
    expect(second.items.single.status, ContentReportStatus.resolved);
    expect(second.nextCursor, isNull);
  });
}
