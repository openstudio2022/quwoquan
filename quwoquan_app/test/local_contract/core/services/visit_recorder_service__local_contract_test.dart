import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_repository.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';

void main() {
  group('VisitRecorderService', () {
    late Directory tempDir;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('visit_recorder_test_');
      Hive.init(tempDir.path);
    });

    tearDown(() async {
      await Hive.deleteFromDisk();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('首次访问会同步到远端仓储', () async {
      final remote = _FakeOpsVisitRepository();
      final service = VisitRecorderService(
        boxName: 'visit_recorder_service_test_remote_sync',
        remoteRepository: remote,
        currentUserId: 'user_001',
      );

      await service.recordVisit(const VisitTarget.page('discovery_recommend'));

      expect(remote.inputs, hasLength(1));
      expect(remote.inputs.first.userId, equals('user_001'));
      expect(remote.inputs.first.targetType, equals('page'));
      expect(remote.inputs.first.targetKey, equals('page_discovery_recommend'));
      expect(remote.inputs.first.source, equals('page_access'));
    });
  });
}

class _FakeOpsVisitRepository implements OpsVisitRepository {
  final List<OpsVisitReportInput> inputs = <OpsVisitReportInput>[];

  @override
  Future<OpsVisitStats> getVisitStats({
    required String targetType,
    required String targetKey,
  }) async {
    return OpsVisitStats.empty;
  }

  @override
  Future<void> recordVisit({required OpsVisitReportInput input}) async {
    inputs.add(input);
  }
}
