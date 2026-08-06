import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/domain/qr_payload_parser.dart';

/// 名片 payload 解析契约：端侧只提取 handle + qr token，交云侧 ResolveProfileQrToken
/// 校验落地，禁止自解析直跳他人主页。
void main() {
  group('QrPayloadParser', () {
    test('从标准名片 URL 提取 handle 与 token', () {
      final result = QrPayloadParser.parse(
        'https://quwoquan.com/u/alice?qr=tok_123',
      );
      expect(result, isNotNull);
      expect(result!.handle, 'alice');
      expect(result.token, 'tok_123');
      expect(result.isValid, isTrue);
    });

    test('缺少 qr token 时返回 null', () {
      expect(
        QrPayloadParser.parse('https://quwoquan.com/u/alice'),
        isNull,
      );
    });

    test('空串/非法 URI 返回 null', () {
      expect(QrPayloadParser.parse(''), isNull);
      expect(QrPayloadParser.parse('   '), isNull);
    });

    test('无 u 段时回退到最后一个路径段作为 handle', () {
      final result = QrPayloadParser.parse(
        'https://quwoquan.com/profile/bob?qr=tok_9',
      );
      expect(result, isNotNull);
      expect(result!.handle, 'bob');
      expect(result.token, 'tok_9');
    });

    test('非趣我圈来源但带 qr token 仍提取 token（落地校验在云侧）', () {
      final result = QrPayloadParser.parse('weird://x?qr=tok_x');
      expect(result, isNotNull);
      expect(result!.token, 'tok_x');
    });
  });
}
