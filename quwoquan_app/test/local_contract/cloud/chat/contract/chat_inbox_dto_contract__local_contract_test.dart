import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('ChatInboxDto — 常规契约', () {
    test('fromMap parses canonical inbox row', () {
      final dto = ChatInboxDto.fromMap(const <String, dynamic>{
        'id': 'conv_006',
        'type': 'group',
        'title': '产品共创群',
        'avatarUrl': 'https://cdn.example.com/group.png',
        'groupAvatarVersion': 1,
        'lastMessagePreview': '今晚 8 点前把评审意见同步到文档里',
        'lastMessageType': 'text',
        'lastMessageTime': '2026-03-18T12:18:00Z',
        'lastSeq': 512,
        'unreadCount': 4,
        'mentionUnreadCount': 2,
        'muted': false,
        'pinned': true,
        'circleId': '',
      });

      expect(dto.id, equals('conv_006'));
      expect(dto.type, equals('group'));
      expect(dto.title, equals('产品共创群'));
      expect(dto.avatarUrl, equals('https://cdn.example.com/group.png'));
      expect(dto.lastMessageType, equals(MessageType.text));
      expect(dto.lastSeq, equals(512));
      expect(dto.unreadCount, equals(4));
      expect(dto.mentionUnreadCount, equals(2));
      expect(dto.hasUnread, isTrue);
      expect(dto.hasMention, isTrue);
      expect(dto.pinned, isTrue);
    });
  });

  group('ChatInboxDto — 单轨契约', () {
    test('拒绝已退休字段，不创建第二套 wire 方言', () {
      expect(
        () => ChatInboxDto.fromMap(const <String, dynamic>{
          '_id': 'current_conv',
          'type': 'group',
          'title': '老字段群聊',
          'memberAvatars': <String>['1.png', '2.png'],
          'lastMessage': '路线图已经发到群文件了',
          'messageType': 'image',
          'lastMessageAt': '2026-03-17T13:00:00Z',
          'maxSeq': 256,
          'unreadCount': 6,
          'mentionCount': 1,
        }),
        throwsFormatException,
      );
    });

    test('toMap round-trip preserves core fields', () {
      final original = ChatInboxDto.fromMap(const <String, dynamic>{
        'id': 'conv_001',
        'type': 'direct',
        'title': '李明',
        'avatarUrl': 'avatar.png',
        'groupAvatarVersion': 0,
        'lastMessagePreview': '好的，明天见',
        'lastMessageType': 'text',
        'lastMessageTime': '2026-03-18T00:32:00Z',
        'lastSeq': 42,
        'unreadCount': 0,
        'mentionUnreadCount': 0,
        'muted': false,
        'pinned': false,
        'circleId': '',
      });

      final roundTrip = ChatInboxDto.fromMap(original.toMap());

      expect(roundTrip.id, equals(original.id));
      expect(roundTrip.title, equals(original.title));
      expect(roundTrip.lastMessagePreview, equals(original.lastMessagePreview));
      expect(roundTrip.lastSeq, equals(original.lastSeq));
      expect(roundTrip.lastMessageTime, equals(original.lastMessageTime));
    });
  });

  group('ChatInboxDto — 异常/边界契约', () {
    test('缺失必填字段立即失败', () {
      expect(() => ChatInboxDto.fromMap(const {}), throwsFormatException);
    });

    test('拒绝 canonical MessageType 以外的历史别名', () {
      final wire = <String, dynamic>{
        'id': 'conv_legacy_type',
        'type': 'direct',
        'title': '历史类型',
        'avatarUrl': '',
        'groupAvatarVersion': 0,
        'lastMessagePreview': '[语音]',
        'lastMessageType': 'voice',
        'lastMessageTime': null,
        'lastSeq': 1,
        'unreadCount': 0,
        'mentionUnreadCount': 0,
        'muted': false,
        'pinned': false,
        'circleId': '',
      };
      expect(() => ChatInboxDto.fromMap(wire), throwsFormatException);
    });
  });
}
