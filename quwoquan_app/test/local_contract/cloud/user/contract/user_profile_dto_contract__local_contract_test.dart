import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:test/test.dart';

void main() {
  test('设置读投影按对象 slice 拆分且与云侧 typed slice 同形', () {
    final notification = decodeNotificationSettingsView(<String, dynamic>{
      'userId': 'u001',
      'enablePush': true,
      'enableMarketing': false,
      'version': 3,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
    expect(notification.userId, 'u001');
    expect(notification.enablePush, isTrue);
    expect(notification.version, 3);

    final privacy = decodePrivacySettingsView(<String, dynamic>{
      'userId': 'u001',
      'allowStrangerMsg': true,
      'profileVisibility': 'private',
      'assistantEnabled': true,
      'blockedKeywords': <String>['spam'],
      'version': 3,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
    expect(privacy.profileVisibility, 'private');
    expect(privacy.blockedKeywords, contains('spam'));

    final call = decodeCallSettingsView(<String, dynamic>{
      'userId': 'u001',
      'defaultIncomingCallRingtoneId': 'official.classic_bell',
      'allowCallerRingtoneOverride': false,
      'enableCallVibration': true,
      'enableGroupCallRing': false,
      'version': 3,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
    expect(
      call.defaultIncomingCallRingtoneId,
      'official.classic_bell',
    );
    expect(call.allowCallerRingtoneOverride, isFalse);
    expect(call.enableGroupCallRing, isFalse);
  });

  test('通话铃声显式 null 保留恢复默认铃声语义', () {
    final call = decodeCallSettingsView(<String, dynamic>{
      'userId': 'u001',
      'defaultIncomingCallRingtoneId': null,
      'allowCallerRingtoneOverride': true,
      'enableCallVibration': true,
      'enableGroupCallRing': true,
      'version': 1,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
    expect(call.defaultIncomingCallRingtoneId, isNull);
  });
}
