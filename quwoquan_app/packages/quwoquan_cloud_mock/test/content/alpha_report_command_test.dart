import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/src/content/alpha_report_command.dart';
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
}
