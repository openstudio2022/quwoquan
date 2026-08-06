import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// CircleBehaviorFact 对外只暴露追加事实能力；实现由 `runtime/di` 注入。
abstract interface class CircleBehaviorFactAppender {
  Future<void> append(AppendCircleBehaviorFactCommand command);
}
