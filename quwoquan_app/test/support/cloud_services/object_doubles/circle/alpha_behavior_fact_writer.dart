import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaCircleBehaviorFactWriter implements CircleBehaviorFactWriter {
  final List<AppendCircleBehaviorFactCommand> accepted =
      <AppendCircleBehaviorFactCommand>[];

  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {
    accepted.add(command);
  }
}
