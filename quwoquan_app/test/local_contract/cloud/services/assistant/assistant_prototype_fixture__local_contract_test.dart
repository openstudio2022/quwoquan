import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/mock/assistant_prototype_fixture.dart';

void main() {
  test('Assistant alpha fixture 只暴露强类型 Assistant 子对象', () {
    final fixture = AssistantPrototypeFixture.instance;

    expect(fixture.memories, isNotEmpty);
    expect(fixture.memories.first.memoryKey, isNotEmpty);
    expect(fixture.tasks, isNotEmpty);
    expect(fixture.tasks.first.taskKey, isNotEmpty);
    expect(fixture.skills, isNotEmpty);
    expect(fixture.skills.first.skillId, isNotEmpty);
  });
}
