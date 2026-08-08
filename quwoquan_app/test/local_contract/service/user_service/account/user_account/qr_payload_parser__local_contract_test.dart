import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/domain/qr_payload_parser.dart';

// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-004

/// 名片 payload 解析契约：端侧只提取 handle + qr token，交云侧 ResolveProfileQrToken
/// 校验落地，禁止自解析直跳他人主页。
void main() {
  final trustedOrigin = Uri.parse('https://quwoquan.com');

  group('QrPayloadParser', () {
    test('从标准名片 URL 提取 handle 与 token', () {
      final result = QrPayloadParser.parse(
        'https://quwoquan.com/u/alice?qr=tok_123',
        trustedPublicOrigin: trustedOrigin,
      );
      expect(result, isNotNull);
      expect(result!.handle, 'alice');
      expect(result.token, 'tok_123');
      expect(result.publicProfileUrl, 'https://quwoquan.com/u/alice');
      expect(result.isValid, isTrue);
    });

    test('缺少 qr token 时返回 null', () {
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
    });

    test('空串/非法 URI 返回 null', () {
      expect(
        QrPayloadParser.parse('', trustedPublicOrigin: trustedOrigin),
        isNull,
      );
      expect(
        QrPayloadParser.parse('   ', trustedPublicOrigin: trustedOrigin),
        isNull,
      );
    });

    test('拒绝非规范路径、scheme 与不可信 host', () {
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/profile/bob?qr=tok_9',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'http://quwoquan.com/u/bob?qr=tok_9',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://evil.example/u/bob?qr=tok_9',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'weird://x/u/bob?qr=tok_x',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
    });

    test('拒绝重复 qr、额外 query 与空白 token', () {
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice?qr=one&qr=two',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice?qr=one&source=share',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice?qr=%20',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice?qr=one&',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://quwoquan.com/u/alice?q%72=one',
          trustedPublicOrigin: trustedOrigin,
        ),
        isNull,
      );
    });

    test('可信 origin 的端口与 payload 必须精确一致', () {
      final gammaOrigin = Uri.parse('https://gamma.quwoquan.com:19443');
      expect(
        QrPayloadParser.parse(
          'https://gamma.quwoquan.com:19443/u/alice?qr=tok_1',
          trustedPublicOrigin: gammaOrigin,
        ),
        isNotNull,
      );
      expect(
        QrPayloadParser.parse(
          'https://gamma.quwoquan.com/u/alice?qr=tok_1',
          trustedPublicOrigin: gammaOrigin,
        ),
        isNull,
      );
    });
  });
}
