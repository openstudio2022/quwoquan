import 'dart:convert';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_run_policy_text_source.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/progress_text_policy.dart';

final class AssistantRunPolicyLoader {
  AssistantRunPolicyLoader({required this.source, required this.path});

  final AssistantRunPolicyTextSource source;
  final String path;

  ProgressTextPolicy? _loaded;
  Future<ProgressTextPolicy>? _loading;

  Future<ProgressTextPolicy> load() {
    final loaded = _loaded;
    if (loaded != null) {
      return Future<ProgressTextPolicy>.value(loaded);
    }
    return _loading ??= _loadOnce();
  }

  Future<ProgressTextPolicy> _loadOnce() async {
    var policy = ProgressTextPolicy.defaults;
    try {
      final decoded = jsonDecode(await source.read(path));
      if (decoded is Map) {
        policy = ProgressTextPolicy.fromJson(decoded.cast<String, dynamic>());
      }
    } catch (_) {
      // 策略是非关键启动增强；资产缺失或损坏时继续使用同一内置默认策略。
    }
    _loaded = policy;
    return policy;
  }
}
