import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';

void main() {
  test('Assistant task fixture 只暴露强类型 task view', () {
    final fixture = AssistantPrototypeFixture.instance;

    expect(fixture.tasks, isNotEmpty);
    expect(fixture.tasks.first.taskKey, isNotEmpty);
  });
}
