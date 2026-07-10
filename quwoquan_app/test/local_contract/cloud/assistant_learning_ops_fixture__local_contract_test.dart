import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';

/// F5: same JSON as [quwoquan_service/contracts/metadata/assistant/assistant_run/fixtures/assistant_learning_ops_summary.sample.json].
File _learningOpsFixtureFile() {
  final candidates = <File>[
    File(
      '../quwoquan_service/contracts/metadata/assistant/assistant_run/fixtures/assistant_learning_ops_summary.sample.json',
    ),
    File(
      'quwoquan_service/contracts/metadata/assistant/assistant_run/fixtures/assistant_learning_ops_summary.sample.json',
    ),
  ];
  for (final f in candidates) {
    if (f.existsSync()) {
      return f;
    }
  }
  throw StateError(
    'assistant_learning_ops_summary.sample.json not found (cwd=${Directory.current.path})',
  );
}

void main() {
  test('AssistantLearningOpsSummaryView decodes shared metadata fixture', () {
    final raw = _learningOpsFixtureFile().readAsStringSync();
    final map = jsonDecode(raw);
    expect(map, isA<Map<String, dynamic>>());
    final v = AssistantLearningOpsSummaryView.fromJson(
      Map<String, dynamic>.from(map as Map),
    );
    expect(v.userId, 'user_fixture_1');
    expect(v.topReasonCodes, hasLength(2));
    expect(v.metricAverages?['answer_relevance'], closeTo(0.72, 1e-9));
  });
}
