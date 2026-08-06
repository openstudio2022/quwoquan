import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';

void main() {
  test('Assistant skill fixture 只暴露强类型 skill view', () {
    final fixture = AssistantPrototypeFixture.instance;

    expect(fixture.skills, isNotEmpty);
    expect(fixture.skills.first.skillId, isNotEmpty);
  });
}
