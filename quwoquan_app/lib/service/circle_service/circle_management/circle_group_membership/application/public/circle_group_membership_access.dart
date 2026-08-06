import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleGroupMembershipAbsentPredicate = bool Function(Object error);

/// 圈子详情页只需的成员关系读取与自助命令 facade。
///
/// 完整管理端口仍由 [CircleGroupMembershipCommands] 与
/// [CircleGroupMembershipQueries] 拥有；此 facade 只把查询侧的 canonical 404
/// 收敛成“尚未加入”，避免 presentation 识别 transport error。
final class CircleGroupMembershipAccess {
  const CircleGroupMembershipAccess({
    required this.commands,
    required this.queries,
    required this.isAbsent,
  });

  final CircleGroupMembershipCommands commands;
  final CircleGroupMembershipQueries queries;
  final CircleGroupMembershipAbsentPredicate isAbsent;

  Future<CircleGroupMembershipSlice?> findMy(
    MyCircleGroupMembershipQuery query,
  ) async {
    try {
      return await queries.getMy(query);
    } catch (error) {
      if (isAbsent(error)) {
        return null;
      }
      rethrow;
    }
  }

  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) => commands.apply(command);

  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) => commands.leave(command);
}
