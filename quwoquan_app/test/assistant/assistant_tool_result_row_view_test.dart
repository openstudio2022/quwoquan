import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row_view.dart';

void main() {
  test('AssistantToolResultRowView reads data payload', () {
    final v = AssistantToolResultRowView(<String, dynamic>{
      'data': <String, dynamic>{'authoritySatisfied': true},
    });
    expect(v.dataPayload['authoritySatisfied'], isTrue);
  });
}
