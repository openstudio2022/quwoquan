import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/assistant/dev/assistant_dev_replay_panel.dart';

/// 助手开发态回放页（壳）；解析与 JSON 展示在 [AssistantDevReplayPanel]。
class AssistantDevReplayPage extends StatelessWidget {
  const AssistantDevReplayPage({
    super.key,
    required this.records,
    required this.loadScoreSnapshot,
  });

  final List<Map<String, Object?>> records;
  final Future<Map<String, Object?>> Function() loadScoreSnapshot;

  @override
  Widget build(BuildContext context) {
    return AssistantDevReplayPanel(
      records: records,
      loadScoreSnapshot: loadScoreSnapshot,
    );
  }
}
