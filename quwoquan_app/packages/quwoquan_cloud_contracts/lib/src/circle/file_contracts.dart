import 'circle_operation_contracts.g.dart';

abstract interface class CircleFileCommandWriter {
  Future<CircleFileCommandResult> create(CreateCircleFileCommand command);

  Future<CircleFileCommandResult> update(UpdateCircleFileCommand command);

  Future<CircleFileCommandResult> delete(DeleteCircleFileCommand command);
}

abstract interface class CircleFileQueryReader {
  Future<CircleFileSlice> get(CircleFileQuery query);

  Future<CircleFilePageSlice> list(CircleFileListQuery query);
}
