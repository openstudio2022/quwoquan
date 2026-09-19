import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final appRoot = Directory.current;

  test('Android 通话能力声明覆盖后台媒体、全屏来电与蓝牙路由', () {
    final manifest = File(
      '${appRoot.path}/android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();

    for (final permission in <String>[
      'android.permission.BLUETOOTH_CONNECT',
      'android.permission.FOREGROUND_SERVICE_PHONE_CALL',
      'android.permission.FOREGROUND_SERVICE_CAMERA',
      'android.permission.FOREGROUND_SERVICE_MICROPHONE',
      'android.permission.USE_FULL_SCREEN_INTENT',
      'android.permission.MANAGE_OWN_CALLS',
    ]) {
      expect(manifest, contains(permission), reason: '缺少 $permission');
    }
    expect(
      manifest,
      contains(
        '<uses-feature android:name="android.hardware.camera.any" '
        'android:required="false" />',
      ),
    );
  });

  test('iOS 用途说明和后台能力明确覆盖音视频通话与 VoIP 来电', () {
    final infoPlist = File('${appRoot.path}/ios/Runner/Info.plist')
        .readAsStringSync();
    final entitlements = File('${appRoot.path}/ios/Runner/Runner.entitlements')
        .readAsStringSync();
    final appDelegate = File('${appRoot.path}/ios/Runner/AppDelegate.swift')
        .readAsStringSync();
    final incomingCallDelegate = File(
      '${appRoot.path}/ios/Runner/AppDelegate+IncomingCall.swift',
    ).readAsStringSync();
    final pushCoordinator = File(
      '${appRoot.path}/ios/Runner/IncomingCallPushCoordinator.swift',
    ).readAsStringSync();

    expect(
      RegExp(
        r'<key>NSCameraUsageDescription</key>\s*<string>[^<]*通话[^<]*</string>',
      ).hasMatch(infoPlist),
      isTrue,
    );
    expect(
      RegExp(
        r'<key>NSMicrophoneUsageDescription</key>\s*<string>[^<]*通话[^<]*</string>',
      ).hasMatch(infoPlist),
      isTrue,
    );
    expect(infoPlist, contains('<key>UIBackgroundModes</key>'));
    expect(infoPlist, contains('<string>voip</string>'));
    expect(infoPlist, contains('<string>audio</string>'));
    expect(infoPlist, contains('<string>remote-notification</string>'));
    expect(entitlements, contains('<key>aps-environment</key>'));
    expect(appDelegate, contains('import PushKit'));
    expect(incomingCallDelegate, contains('PKPushRegistryDelegate'));
    expect(incomingCallDelegate, contains('didReceiveIncomingPushWith'));
    expect(pushCoordinator, contains('private(set) var pushRegistry'));
    expect(pushCoordinator, contains('showCallkitIncoming'));
    expect(pushCoordinator, contains('completionOnce.call()'));
    expect(pushCoordinator, contains('pending_actions'));
    expect(pushCoordinator, contains('apns_voip'));
    expect(pushCoordinator, contains('IncomingCallKeychainStore'));
    expect(
      pushCoordinator,
      contains('kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly'),
    );
    expect(pushCoordinator, contains('envelope.action == "cancel"'));
    expect(pushCoordinator, contains('.now() + 4.5'));
    expect(
      pushCoordinator,
      isNot(contains('defaults.set(token, forKey: StoreKey.voipToken)')),
    );
    expect(incomingCallDelegate, contains('didInvalidatePushTokenFor'));
    expect(pushCoordinator, isNot(contains('URLSession')));
    expect(pushCoordinator, isNot(contains('callerAvatar')));
    expect(
      RegExp(
        r'showCallkitIncoming\([^;]+\)\s*\{.*completionOnce\.call\(\)',
        dotAll: true,
      ).hasMatch(pushCoordinator),
      isTrue,
    );
    expect(
      incomingCallDelegate,
      contains('QuwoquanIncomingCallBootstrapPlugin'),
    );
    expect(
      RegExp(r'forPlugin:\s*"FlutterCallkitIncomingPlugin"')
          .hasMatch(incomingCallDelegate),
      isFalse,
      reason: '官方 CallKit plugin key 必须只由 GeneratedPluginRegistrant 占用',
    );
    expect(
      incomingCallDelegate.indexOf(
        'SwiftFlutterCallkitIncomingPlugin.register',
      ),
      lessThan(
        incomingCallDelegate.indexOf(
          'incomingCallPushCoordinator.startPushKit',
        ),
      ),
    );
  });

  test('Android startup and dependencies are Google-service-free', () {
    final sources =
        <String>[
              'configs/plugin_registration_policy.json',
              'android/settings.gradle.kts',
              'android/build.gradle.kts',
              'android/app/build.gradle.kts',
              'android/app/src/main/java/com/quwoquan/quwoquan_app/StartupEagerPluginRegistry.java',
              'lib/runtime/shell/startup/app_bootstrap.dart',
              'pubspec.yaml',
              'pubspec.lock',
            ]
            .map((path) => File('${appRoot.path}/$path').readAsStringSync())
            .join('\n');
    for (final forbidden in <String>[
      'firebase_core',
      'firebase_messaging',
      'com.google.gms.google-services',
      'com.google.firebase.crashlytics',
      'com.google.android.gms:play-services',
      'google-'
          'services.json',
      'google_app_id',
      'mobile_scanner',
    ]) {
      expect(sources, isNot(contains(forbidden)), reason: forbidden);
    }
    expect(sources, contains('FlutterCallkitIncomingPlugin'));
    expect(sources, contains('androidx.core:core-splashscreen'));
    expect(sources, contains('google()'));
  });
}
