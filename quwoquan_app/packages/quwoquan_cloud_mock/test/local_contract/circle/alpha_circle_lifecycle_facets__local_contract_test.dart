import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  group('AlphaCircleLifecycleFacet 与远端命令契约同型', () {
    late AlphaCircleLifecycleFacet lifecycle;

    setUp(() {
      lifecycle = AlphaCircleLifecycleFacet();
    });

    test('createCircle 返回稳定回执并按意图幂等重放', () async {
      final created = await lifecycle.createCircle(
        CreateCircleCommand(name: '测试圈子', category: 'tech'),
      );
      expect(created.circleId, isNotEmpty);
      expect(created.version, 1);
      expect(created.status, CircleLifecycleStatus.active);
      expect(created.idempotentReplay, isFalse);

      final replayed = await lifecycle.createCircle(
        CreateCircleCommand(name: '测试圈子', category: 'tech'),
      );
      expect(replayed.circleId, created.circleId);
      expect(replayed.idempotentReplay, isTrue);
    });

    test('updateCircle / updateCircleSections 推进版本', () async {
      final created = await lifecycle.createCircle(
        CreateCircleCommand(name: '版本圈'),
      );
      final updated = await lifecycle.updateCircle(
        UpdateCircleCommand(circleId: created.circleId, name: '新名称'),
      );
      expect(updated.version, created.version + 1);

      final sections = await lifecycle.updateCircleSections(
        UpdateCircleSectionsCommand(
          circleId: created.circleId,
          sections: [
            CircleSectionConfigInput(
              sectionType: 'works',
              visible: true,
              order: 0,
            ),
          ],
        ),
      );
      expect(sections.version, updated.version + 1);
    });

    test('archiveCircle 已归档时重放原回执（no-op receipt 语义）', () async {
      final created = await lifecycle.createCircle(
        CreateCircleCommand(name: '归档圈'),
      );
      final archived = await lifecycle.archiveCircle(
        ArchiveCircleCommand(circleId: created.circleId),
      );
      expect(archived.status, CircleLifecycleStatus.archived);
      expect(archived.idempotentReplay, isFalse);

      final noop = await lifecycle.archiveCircle(
        ArchiveCircleCommand(circleId: created.circleId),
      );
      expect(noop.version, archived.version);
      expect(noop.status, CircleLifecycleStatus.archived);
      expect(noop.idempotentReplay, isTrue);
    });
  });
}
