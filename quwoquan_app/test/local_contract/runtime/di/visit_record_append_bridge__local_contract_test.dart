import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/application/public/visit_record_writer.dart';
import 'package:quwoquan_app/runtime/di/visit_record_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/visit/visit_append_port.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';

void main() {
  test(
    'bridge maps the closed runtime target set to canonical enums',
    () async {
      final writer = _RecordingVisitRecordWriter();
      final bridge = VisitRecordAppendBridge(writer);
      const expected = <String, VisitTargetType>{
        'page': VisitTargetType.page,
        'post': VisitTargetType.post,
        'circle': VisitTargetType.circle,
        'user': VisitTargetType.user,
      };

      for (final entry in expected.entries) {
        await bridge.recordVisit(
          VisitAppendInput(
            idempotencyKey: 'visit-${entry.key}',
            targetType: entry.key,
            targetKey: '${entry.key}-1',
          ),
        );
        expect(writer.requests.last.targetType, entry.value);
        expect(writer.idempotencyKeys.last, 'visit-${entry.key}');
      }
    },
  );

  test(
    'bridge rejects unknown targets and blank idempotency before mutation',
    () async {
      final writer = _RecordingVisitRecordWriter();
      final bridge = VisitRecordAppendBridge(writer);

      await expectLater(
        bridge.recordVisit(
          const VisitAppendInput(
            idempotencyKey: 'visit-unknown',
            targetType: 'unknown',
            targetKey: 'unknown-1',
          ),
        ),
        throwsArgumentError,
      );
      await expectLater(
        bridge.recordVisit(
          const VisitAppendInput(
            idempotencyKey: ' ',
            targetType: 'page',
            targetKey: 'page-1',
          ),
        ),
        throwsArgumentError,
      );
      expect(writer.requests, isEmpty);
    },
  );

  test('runtime storage codec rejects Cloud aliases and unknown fields', () {
    expect(
      () => VisitAppendInput.fromStorageJson(<String, dynamic>{
        'idempotencyKey': 'visit-intent-1',
        'targetType': 'page',
        'targetKey': 'page_home',
        'userId': 'must-not-be-accepted',
      }),
      throwsFormatException,
    );
  });
}

final class _RecordingVisitRecordWriter implements VisitRecordWriter {
  final List<RecordVisitRequest> requests = <RecordVisitRequest>[];
  final List<String> idempotencyKeys = <String>[];

  @override
  Future<RecordVisitReceipt> recordVisit(
    RecordVisitRequest request, {
    required String idempotencyKey,
  }) async {
    requests.add(request);
    idempotencyKeys.add(idempotencyKey);
    return RecordVisitReceipt(
      targetType: request.targetType,
      targetKey: request.targetKey,
      visitCount: 1,
      occurredAt: DateTime.utc(2026, 8, 5),
      replayed: false,
    );
  }
}
