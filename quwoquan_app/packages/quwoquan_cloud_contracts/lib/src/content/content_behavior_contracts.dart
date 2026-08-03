import 'content_operation_contracts.g.dart';

abstract interface class ContentBehaviorCommandWriter {
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command);
}
