import 'circle_operation_contracts.g.dart';

abstract interface class CircleLifecycleCommandWriter {
  Future<CircleCommandResult> createCircle(CreateCircleCommand command);

  Future<CircleCommandResult> updateCircle(UpdateCircleCommand command);

  Future<CircleCommandResult> archiveCircle(ArchiveCircleCommand command);
}

abstract interface class CircleConfigurationCommandWriter {
  Future<CircleCommandResult> updateCircleSections(
    UpdateCircleSectionsCommand command,
  );
}
