import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/user/account/credential_binding/domain/phone_number_wire.dart';

void main() {
  group('mainland phone command wire', () {
    test('11 位 UI 输入在 command 边界收敛为 E.164', () {
      expect(mainlandPhoneLocalDigitsOrEmpty('180 1381 9016'), '18013819016');
      expect(mainlandPhoneE164OrEmpty('180 1381 9016'), '+8618013819016');
    });

    test('已经规范化的 E.164 输入保持幂等', () {
      expect(mainlandPhoneLocalDigitsOrEmpty('+8618013819016'), '18013819016');
      expect(mainlandPhoneE164OrEmpty('+8618013819016'), '+8618013819016');
    });

    test('无效大陆手机号不会进入 command wire', () {
      for (final value in <String>['', '12013819016', '+85290123456']) {
        expect(isValidMainlandPhoneNumber(value), isFalse, reason: value);
        expect(mainlandPhoneE164OrEmpty(value), isEmpty, reason: value);
      }
    });
  });
}
