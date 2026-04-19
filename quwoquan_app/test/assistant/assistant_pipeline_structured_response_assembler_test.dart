import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_structured_response_assembler.dart';
import 'package:test/test.dart';

void main() {
  test('assembleStructuredResponseRoot merges enriched payload and root payload', () {
    final merged = assembleStructuredResponseRoot(
      enrichedAnswerPayload: <String, dynamic>{
        'answer': 'ok',
        'sharedKey': 'from_enriched',
      },
      rootPayload: <String, dynamic>{
        'domainId': 'content',
        'sharedKey': 'from_root',
      },
    );

    expect(merged['answer'], 'ok');
    expect(merged['domainId'], 'content');
    expect(merged['sharedKey'], 'from_root');
  });
}
