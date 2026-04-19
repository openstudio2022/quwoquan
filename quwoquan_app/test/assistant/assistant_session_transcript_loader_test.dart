import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/session/session_transcript_service.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';

void main() {
  test('loadTranscriptRowsFromSessionDetail splits visible and hidden by pageSize',
      () async {
    final messages = List<AssistantSessionWireMessage>.generate(
      20,
      (i) => AssistantSessionWireMessage.fromJson(<String, dynamic>{
        'role': i.isEven ? 'user' : 'assistant',
        'content': 'text$i',
      }),
    );
    final detail = AssistantSessionWireDetail(
      sessionId: 's1',
      messages: messages,
    );
    final result = await loadTranscriptRowsFromSessionDetail(
      detail: detail,
      pageSize: 18,
      profileSubjectId: 'user_test',
      normalizeAssistantContentForModel: (m) =>
          (m['content'] ?? '').toString(),
    );
    expect(result.visibleRows, hasLength(18));
    expect(result.hiddenRows, hasLength(2));
  });
}
