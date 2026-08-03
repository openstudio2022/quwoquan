import 'circle_operation_contracts.g.dart';

abstract interface class CircleBehaviorFactWriter {
  Future<void> append(AppendCircleBehaviorFactCommand command);
}
