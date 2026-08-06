import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_hash_service.dart';

/// 端云一致哈希契约：与服务端 `phonematch__local_contract_test.go` 共享同一锁定向量，
/// 任一端规范化/哈希漂移都会在 CI 立刻暴露（手机号原文永不出库、不上行）。
void main() {
  const service = ContactHashService();

  // 与 Go phonematch.Hash("13800138000") 完全一致。
  const lockedVector =
      'ec1a7eb3a4a2d69b978580e3d74fc3677cb2b4ebc2e1a58be568310147539484';

  group('ContactHashService', () {
    test('锁定向量与服务端一致（13800138000）', () {
      expect(service.hash('13800138000'), lockedVector);
    });

    test('等价手机号写法收敛到同一规范形与哈希', () {
      const forms = <String>[
        '13800138000',
        '+8613800138000',
        '86 138 0013 8000',
        '138-0013-8000',
        '(138) 0013 8000',
      ];
      for (final form in forms) {
        expect(
          service.canonicalize(form),
          '+8613800138000',
          reason: 'canonicalize($form)',
        );
        expect(service.hash(form), lockedVector, reason: 'hash($form)');
      }
    });

    test('空/无效输入返回空串', () {
      for (final form in <String>['', '   ', '()', '+']) {
        expect(service.canonicalize(form), '', reason: 'canonicalize($form)');
        expect(service.hash(form), '', reason: 'hash($form)');
      }
    });

    test('hashAll 跳过空号并按稳定顺序去重', () {
      final hashes = service.hashAll(<String>[
        '13800138000',
        '+8613800138000', // 与上等价 → 去重
        '',
        '13900139000',
      ]);
      expect(hashes, hasLength(2));
      expect(hashes.first, lockedVector);
      expect(hashes.toSet().length, 2);
    });
  });
}
