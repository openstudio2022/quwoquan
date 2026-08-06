import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class CircleBehaviorFactTypedDouble
    implements CircleBehaviorFactAppender {
  final List<AppendCircleBehaviorFactCommand> accepted =
      <AppendCircleBehaviorFactCommand>[];

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {
    accepted.add(command);
  }
}
