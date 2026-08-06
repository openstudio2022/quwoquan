import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_provider_bridge.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('活跃分身未就绪使用结构化可恢复 RuntimeFailure', () {
    final failure = ActivePersonaContextUnavailableFailure();

    expect(failure.code, ContentErrorCode.requiredDependencyUnavailable.code);
    expect(failure.semanticReason, 'active_persona_context_unavailable');
    expect(failure.kind, RuntimeFailureKind.unavailable);
    expect(failure.nature, RuntimeFailureNature.transient);
    expect(failure.recovery.action, 'retry');
    expect(failure.recovery.disruptionLevel, 'surface');
  });
}
