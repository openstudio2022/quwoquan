import 'package:flutter_test/flutter_test.dart';

import '../../../../support/cloud_services/assistant_facets_mock.dart';

void main() {
  test('Assistant alpha fixture 只暴露强类型 Assistant 子对象', () {
    final fixture = AssistantPrototypeFixture.instance;

    expect(fixture.tasks, isNotEmpty);
    expect(fixture.tasks.first.taskKey, isNotEmpty);
    expect(fixture.skills, isNotEmpty);
    expect(fixture.skills.first.skillId, isNotEmpty);
  });
}
