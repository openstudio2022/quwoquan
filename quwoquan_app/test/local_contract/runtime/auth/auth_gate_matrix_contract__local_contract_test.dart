import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('AuthGate 矩阵与 API 鉴权快照交叉校验', () {
    test('每个受限入口声明的 requiredOperation 在快照中必须是 required', () {
      final violations = <String>[];
      for (final entry in authGateMatrix.values) {
        for (final op in entry.requiredOperations) {
          final operation = appCloudOperationContracts[op];
          if (operation == null) {
            violations.add('${entry.reason.name}: operation $op 不存在于鉴权快照');
          } else if (operation.authMode != 'required') {
            violations.add(
              '${entry.reason.name}: operation $op 鉴权模式为 '
              '${operation.authMode}，应为 required',
            );
          }
        }
      }
      expect(violations, isEmpty, reason: violations.join('\n'));
    });

    test('每个 AuthGateReason 都有非空标题与提示', () {
      for (final reason in AuthGateReason.values) {
        expect(reason.title.trim(), isNotEmpty);
        expect(reason.prompt.trim(), isNotEmpty);
      }
    });

    test('authGateTitleForReasonName 能解析 reason 名并对未知名返回 null', () {
      expect(
        authGateTitleForReasonName(AuthGateReason.comment.name),
        AuthGateReason.comment.title,
      );
      expect(authGateTitleForReasonName('not_a_reason'), isNull);
      expect(authGateTitleForReasonName(null), isNull);
      expect(authGateTitleForReasonName(''), isNull);
    });

    test('canonical operation contract 鉴权模式一致', () {
      expect(
        appCloudOperationContracts[AppCloudOperationIds
                .contentPostSubmitPostPublication]
            ?.authMode,
        'required',
      );
      expect(
        appCloudOperationContracts[AppCloudOperationIds
                .integrationLocationSearchLocations]
            ?.authMode,
        'optional',
      );
      expect(
        appCloudOperationContracts[AppCloudOperationIds
                .contentPostSubmitPostPublication]
            ?.canonicalOperationId,
        AppCloudOperationIds.contentPostSubmitPostPublication,
      );
    });
  });
}
