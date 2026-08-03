import 'circle_operation_contracts.g.dart';

abstract interface class CircleGroupCommandWriter {
  Future<CircleGroupCommandResult> create(CreateCircleGroupCommand command);

  Future<CircleGroupCommandResult> update(UpdateCircleGroupCommand command);

  Future<CircleGroupCommandResult> archive(ArchiveCircleGroupCommand command);
}

abstract interface class CircleGroupQueryReader {
  Future<CircleGroupSlice> get(CircleGroupQuery query);

  Future<CircleGroupPageSlice> list(CircleGroupListQuery query);

  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query);
}
