import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/rtc/mock/rtc_mock_data.dart';

void main() {
  group('kMockCallSessions — 与 metadata CallStatus 对齐', () {
    test('主会话使用合法 status 取值', () {
      for (final row in kMockCallSessions) {
        final s = row.status;
        expect(
          const {
            'initiated',
            'ringing',
            'connecting',
            'in_call',
            'ended',
          },
          contains(s),
          reason: 'status=$s 应在 fields.yaml CallStatus 枚举内',
        );
      }
    });

    test('主键与 roomId 存在', () {
      for (final row in kMockCallSessions) {
        expect(row.id, isNotEmpty);
        expect(row.roomId, isNotEmpty);
      }
    });
  });
}
