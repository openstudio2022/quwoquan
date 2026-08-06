// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/observability/visit/visit_append_port.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';

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

    test('首次访问会同步到远端强类型写面', () async {
      final remote = _RecordingVisitWriter();
      final service = VisitRecorderService(
        boxName: 'visit_recorder_service_test_remote_sync',
        remoteWriter: remote,
      );

      await service.recordVisit(const VisitTarget.page('discovery_recommend'));

      expect(remote.inputs, hasLength(1));
      final input = remote.inputs.first;
      expect(input.targetType, equals('page'));
      expect(input.targetKey, equals('page_discovery_recommend'));
      expect(input.idempotencyKey, isNotEmpty);
      // 本地补传 storage codec 保存三个必需字段；Cloud wire
      // 由 generated RecordVisitRequest encoder 独立生成。
      expect(
        input.toStorageJson().keys,
        unorderedEquals(<String>['idempotencyKey', 'targetType', 'targetKey']),
      );
    });

    test('五分钟去重窗口内的重复访问不产生第二次上报', () async {
      final remote = _RecordingVisitWriter();
      final service = VisitRecorderService(
        boxName: 'visit_recorder_service_test_dedup',
        remoteWriter: remote,
      );

      await service.recordVisit(const VisitTarget.page('circle_detail'));
      await service.recordVisit(const VisitTarget.page('circle_detail'));

      expect(remote.inputs, hasLength(1));
    });

    test('上报失败入队补传并持久化同一幂等键', () async {
      final remote = _RecordingVisitWriter(failFirst: true);
      final service = VisitRecorderService(
        boxName: 'visit_recorder_service_test_retry',
        remoteWriter: remote,
      );

      await service.recordVisit(const VisitTarget.page('interest_match'));
      // recordVisit 内的远端同步是 fire-and-forget：轮询等待失败输入
      // 完成入队（enqueue 本身也是异步的）。
      final pendingBox = await Hive.openBox<String>(kVisitPendingSyncBoxName);
      for (var i = 0; i < 40 && pendingBox.isEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 50));
      }

      expect(remote.failedInputs, hasLength(1));
      final failed = remote.failedInputs.single;
      expect(failed.idempotencyKey, isNotEmpty);

      // 失败输入以 storage 形状进入补传队列，幂等键原样保留——
      // 补传重放与首次尝试对服务端是同一次业务访问。
      expect(pendingBox.values, hasLength(1));
      final persisted = VisitAppendInput.fromStorageJson(
        jsonDecode(pendingBox.values.single) as Map<String, dynamic>,
      );
      expect(persisted.idempotencyKey, equals(failed.idempotencyKey));
      expect(persisted.targetKey, equals(failed.targetKey));
    });

    test('账号 closed 终态清空访问画像和补传回执并停止旧实例记录', () async {
      const recordsBoxName = 'visit_recorder_service_test_closed';
      final service = VisitRecorderService(boxName: recordsBoxName);
      await service.recordVisit(const VisitTarget.page('account_security'));
      final recordsBox = Hive.box<String>(recordsBoxName);
      final pendingBox = await Hive.openBox<String>(kVisitPendingSyncBoxName);
      await pendingBox.put('pending', '{"targetKey":"sensitive"}');
      expect(recordsBox, isNotEmpty);
      expect(pendingBox, isNotEmpty);

      await service.clearForTerminalAccountClosure();

      expect(recordsBox, isEmpty);
      expect(pendingBox, isEmpty);
      await service.recordVisit(const VisitTarget.page('after_closed'));
      expect(recordsBox, isEmpty);
    });
  });
}

class _RecordingVisitWriter implements VisitAppendPort {
  _RecordingVisitWriter({this.failFirst = false});

  final bool failFirst;
  final List<VisitAppendInput> inputs = <VisitAppendInput>[];
  final List<VisitAppendInput> failedInputs = <VisitAppendInput>[];
  var _calls = 0;

  @override
  Future<void> recordVisit(VisitAppendInput input) async {
    _calls++;
    if (failFirst && _calls == 1) {
      failedInputs.add(input);
      throw StateError('simulated network failure');
    }
    inputs.add(input);
  }
}
