import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// CircleGroup 的公开命令边界。
abstract interface class CircleGroupCommands {
  Future<CircleGroupCommandResult> create(CreateCircleGroupCommand command);

  Future<CircleGroupCommandResult> update(UpdateCircleGroupCommand command);

  Future<CircleGroupCommandResult> archive(ArchiveCircleGroupCommand command);
}

/// CircleGroup 的公开查询边界。
abstract interface class CircleGroupQueries {
  Future<CircleGroupSlice> get(CircleGroupQuery query);

  Future<CircleGroupPageSlice> list(CircleGroupListQuery query);

  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query);
}
