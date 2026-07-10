import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_transcript_bubble_envelope.dart';

void main() {
  test('task_card: envelope matches codec map for tasks', () {
    final row = UserTranscriptTimelineRow(
      id: 'r1',
      conversationId: 'c1',
      type: 'task_card',
      content: '',
      senderId: 'u1',
      senderName: 'U',
      extra: <String, dynamic>{
        'tasks': <Map<String, dynamic>>[
          <String, dynamic>{'title': 'T1', 'done': false},
        ],
      },
    );
    final map = PersistedTimelineTurnCodec.encode(row);
    final env = AssistantTranscriptBubbleEnvelope.fromCodecMap(map);
    expect(env.taskItems.length, 1);
    expect(env.taskItems.first['title'], 'T1');
  });

  test('image: thumbnailUrl and imageUrl fallbacks', () {
    final row = UserTranscriptTimelineRow(
      id: 'r2',
      conversationId: 'c1',
      type: 'image',
      content: '',
      senderId: 'u1',
      senderName: 'U',
      extra: <String, dynamic>{'thumbnailUrl': ' https://img/thumb '},
    );
    final map = PersistedTimelineTurnCodec.encode(row);
    final env = AssistantTranscriptBubbleEnvelope.fromCodecMap(map);
    expect(env.imageUrl, 'https://img/thumb');
  });

  test('audio: media map and current fields', () {
    final row = UserTranscriptTimelineRow(
      id: 'r3',
      conversationId: 'c1',
      type: 'audio',
      content: '',
      senderId: 'u1',
      senderName: 'U',
      isRead: false,
      extra: <String, dynamic>{
        '_id': 'mid',
        'messageStatus': 'delivered',
        'media': <String, dynamic>{
          'url': 'https://a/audio',
          'durationMs': 1200,
          'waveform': <num>[0.1, 0.2],
        },
      },
    );
    final map = PersistedTimelineTurnCodec.encode(row);
    final env = AssistantTranscriptBubbleEnvelope.fromCodecMap(map);
    expect(env.audioMediaUrl, 'https://a/audio');
    expect(env.audioDurationMs, 1200);
    expect(env.audioWaveform, [0.1, 0.2]);
    expect(env.audioMessageId, 'mid');
    expect(env.audioMessageStatus, 'delivered');
    expect(env.audioIsRead, isFalse);
  });
}
