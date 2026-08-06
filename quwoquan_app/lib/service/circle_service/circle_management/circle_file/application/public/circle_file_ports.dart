import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// CircleFile 的公开写入边界。
///
/// application 只暴露对象语义；generated client 与调用上下文由 adapter 处理。
abstract interface class CircleFileWriter {
  Future<CircleFileCommandResult> create(CreateCircleFileCommand command);

  Future<CircleFileCommandResult> update(UpdateCircleFileCommand command);

  Future<CircleFileCommandResult> delete(DeleteCircleFileCommand command);
}

/// CircleFile 的公开读取边界。
abstract interface class CircleFileReader {
  Future<CircleFileSlice> get(CircleFileQuery query);

  Future<CircleFilePageSlice> list(CircleFileListQuery query);
}
