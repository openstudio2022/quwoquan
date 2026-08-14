// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-004
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/message-interaction-polish/spec.md#open-004
// readiness_case: message_send_message_app_api
// readiness_case: message_list_messages_app_api
//
// App Remote 媒体链与 replyTo 的 api_integration：
// 1) 真实 MediaAsset 上传（init -> 预签名 PUT -> complete -> ready）后经
//    production Remote 发送 audio 消息，list/sync 读回 audioDurationMs 与
//    audioWaveform 原值；
// 2) replyToMessageId 经 Remote 正例持久且幂等重放同源，负例（悬空引用）
//    走 canonical message_invalid 失败，不产生伪成功。
@Timeout(Duration(minutes: 4))
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;
  var harnessReady = false;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    harnessReady = true;
    conversationId = await harness.seedConversation();
  });
  tearDownAll(() async {
    if (harnessReady) {
      await harness.close();
    }
  });

  test('真实 MediaAsset 上传后 audio 元数据经 Remote 全链读回', () async {
    final assetId = await harness.uploadReadyAudioAsset();
    const waveform = <double>[0.1, 0.5, 0.9, 0.4, 0.2];
    final clientMsgId =
        'l3-audio-${DateTime.now().microsecondsSinceEpoch}';
    final sent = await harness.messageCommands.sendMessage(
      ChatSendMessageCommand(
        conversationId: conversationId,
        type: 'audio',
        content: '',
        clientMsgId: clientMsgId,
        mediaAssetId: assetId,
        audioDurationMs: 3200,
        audioWaveform: waveform,
        mentions: const <String>[],
      ),
    );
    expect(sent.seq, greaterThan(0));

    final listed = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 20,
    );
    final audio = listed
        .where((message) => message.clientMsgId == clientMsgId)
        .single;
    expect(audio.type, 'audio');
    expect(audio.mediaAssetId, assetId);
    expect(audio.audioDurationMs, 3200, reason: '语音时长必须原值读回');
    expect(audio.audioWaveform, waveform, reason: '波形必须原值读回');
    expect(
      audio.mediaDeliveryUrl,
      isNotNull,
      reason: '读面必须组合 MediaAsset 交付字段',
    );

    final synced = await harness.repository.syncMessages(
      conversationId: conversationId,
      lastSeq: sent.seq - 1,
      limit: 10,
    );
    final syncedAudio = synced.messages
        .where((message) => message.clientMsgId == clientMsgId)
        .single;
    expect(syncedAudio.audioDurationMs, 3200);
    expect(syncedAudio.audioWaveform, waveform);
  });

  test('replyTo 经 Remote 持久、幂等重放同源，悬空引用 canonical 失败', () async {
    final target = await harness.sendMessage(
      conversationId,
      'l3-reply-target-${DateTime.now().microsecondsSinceEpoch}',
    );
    final replyClientMsgId =
        'l3-reply-${DateTime.now().microsecondsSinceEpoch}';
    final reply = await harness.messageCommands.sendMessage(
      ChatSendMessageCommand(
        conversationId: conversationId,
        type: 'text',
        content: '引用回复 Remote 正例',
        clientMsgId: replyClientMsgId,
        replyToMessageId: target.messageId,
        mentions: const <String>[],
      ),
    );
    final replay = await harness.messageCommands.sendMessage(
      ChatSendMessageCommand(
        conversationId: conversationId,
        type: 'text',
        content: '引用回复 Remote 正例',
        clientMsgId: replyClientMsgId,
        replyToMessageId: target.messageId,
        mentions: const <String>[],
      ),
    );
    expect(replay.messageId, reply.messageId, reason: '幂等重放必须同源');

    final listed = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 20,
    );
    final persisted = listed
        .where((message) => message.clientMsgId == replyClientMsgId)
        .single;
    expect(
      persisted.replyToMessageId,
      target.messageId,
      reason: 'replyTo 引用必须随读面返回',
    );

    await expectLater(
      harness.messageCommands.sendMessage(
        ChatSendMessageCommand(
          conversationId: conversationId,
          type: 'text',
          content: '悬空引用必须被拒',
          clientMsgId:
              'l3-reply-dangling-${DateTime.now().microsecondsSinceEpoch}',
          replyToMessageId:
              'missing-${DateTime.now().microsecondsSinceEpoch}',
          mentions: const <String>[],
        ),
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          400,
        ),
      ),
      reason: '悬空 replyTo 引用必须 canonical 失败而非伪成功',
    );
  });
}
