import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test(
    'Alpha CircleGroup fixture preserves typed lifecycle and version',
    () async {
      final facet = AlphaCircleGroupFacet();
      final created = await facet.create(
        CreateCircleGroupCommand(
          circleId: 'circle_alpha',
          groupType: CircleGroupType.selfBuilt,
          name: 'Alpha 兴趣群',
          visibility: CircleGroupVisibility.private,
          joinPolicy: CircleGroupJoinPolicy.applyOnly,
          storageEnabled: true,
          noticeEnabled: true,
        ),
      );

      final updated = await facet.update(
        UpdateCircleGroupCommand(
          circleId: 'circle_alpha',
          groupId: created.groupId,
          expectedVersion: created.version,
          name: 'Alpha 兴趣群 2',
        ),
      );
      final archived = await facet.archive(
        ArchiveCircleGroupCommand(
          circleId: 'circle_alpha',
          groupId: created.groupId,
        ),
      );
      final stored = await facet.get(
        CircleGroupQuery(circleId: 'circle_alpha', groupId: created.groupId),
      );

      expect(stored.name, 'Alpha 兴趣群 2');
      expect(archived.status, CircleGroupStatus.archived);
      expect(stored.version, 3);
    },
  );

  test(
    'Alpha CircleGroupMembership fixture uses server-owned transitions',
    () async {
      final facet = AlphaCircleGroupMembershipFacet();
      final applied = await facet.apply(
        ApplyCircleGroupMembershipCommand(
          circleId: 'circle_alpha',
          groupId: 'group_alpha',
        ),
      );
      final replay = await facet.apply(
        ApplyCircleGroupMembershipCommand(
          circleId: 'circle_alpha',
          groupId: 'group_alpha',
        ),
      );
      final approved = await facet.approve(
        DecideCircleGroupMembershipCommand(
          circleId: 'circle_alpha',
          groupId: 'group_alpha',
          personaId: 'alpha_persona',
        ),
      );

      expect(applied.state, CircleGroupMembershipState.pending);
      expect(replay.idempotentReplay, isTrue);
      expect(approved.state, CircleGroupMembershipState.active);
      final left = await facet.leave(
        LeaveCircleGroupMembershipCommand(
          circleId: 'circle_alpha',
          groupId: 'group_alpha',
        ),
      );
      expect(left.state, CircleGroupMembershipState.left);
    },
  );
}
