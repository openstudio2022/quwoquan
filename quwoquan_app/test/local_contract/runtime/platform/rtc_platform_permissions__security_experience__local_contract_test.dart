import 'dart:convert';
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
    final infoPlist = File(
      '${appRoot.path}/ios/Runner/Info.plist',
    ).readAsStringSync();
    final entitlements = File(
      '${appRoot.path}/ios/Runner/Runner.entitlements',
    ).readAsStringSync();
    final appDelegate = File(
      '${appRoot.path}/ios/Runner/AppDelegate.swift',
    ).readAsStringSync();
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
      RegExp(
        r'forPlugin:\s*"FlutterCallkitIncomingPlugin"',
      ).hasMatch(incomingCallDelegate),
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

  test('CallKit/FCM 是 startup-critical 且后台 handler 不直接拉起 Activity', () {
    final pluginPolicy = File(
      '${appRoot.path}/configs/plugin_registration_policy.json',
    ).readAsStringSync();
    final deferredRegistry = File(
      '${appRoot.path}/android/app/src/main/java/com/quwoquan/quwoquan_app/'
      'StartupDeferredPluginRegistry.java',
    ).readAsStringSync();
    final eagerRegistry = File(
      '${appRoot.path}/android/app/src/main/java/com/quwoquan/quwoquan_app/'
      'StartupEagerPluginRegistry.java',
    ).readAsStringSync();
    final firebaseRuntime = File(
      '${appRoot.path}/lib/runtime/platform/firebase_incoming_call_runtime.dart',
    ).readAsStringSync();
    final bootstrap = File(
      '${appRoot.path}/lib/runtime/shell/startup/app_bootstrap.dart',
    ).readAsStringSync();
    final pushEndpointGateway = File(
      '${appRoot.path}/lib/runtime/platform/push_endpoint_gateway.dart',
    ).readAsStringSync();
    final incomingCallPresenter = File(
      '${appRoot.path}/lib/runtime/platform/incoming_call_native_presenter.dart',
    ).readAsStringSync();
    final androidSettings = File(
      '${appRoot.path}/android/settings.gradle.kts',
    ).readAsStringSync();
    final androidAppBuild = File(
      '${appRoot.path}/android/app/build.gradle.kts',
    ).readAsStringSync();
    final androidNativeBridge = File(
      '${appRoot.path}/android/app/src/main/java/com/quwoquan/quwoquan_app/'
      'IncomingCallNativeBridgePlugin.java',
    ).readAsStringSync();
    final iosCallKitPlugin = File(
      '${appRoot.path}/vendor/plugins/flutter_callkit_incoming/ios/'
      'flutter_callkit_incoming/Classes/SwiftFlutterCallkitIncomingPlugin.swift',
    ).readAsStringSync();
    final androidCallKitPlugin = File(
      '${appRoot.path}/vendor/plugins/flutter_callkit_incoming/android/src/'
      'main/kotlin/com/hiennv/flutter_callkit_incoming/'
      'FlutterCallkitIncomingPlugin.kt',
    ).readAsStringSync();
    final decodedPolicy = jsonDecode(pluginPolicy) as Map<String, Object?>;
    final eagerPlugins = (decodedPolicy['eagerRuntime'] as List).cast<String>();
    final deferredRtcPlugins = (decodedPolicy['rtc'] as List).cast<String>();
    expect(
      pluginPolicy,
      contains(
        '"com.hiennv.flutter_callkit_incoming.'
        'FlutterCallkitIncomingPlugin"',
      ),
    );
    expect(
      eagerPlugins,
      contains(
        'com.hiennv.flutter_callkit_incoming.'
        'FlutterCallkitIncomingPlugin',
      ),
    );
    expect(
      eagerPlugins,
      contains('io.flutter.plugins.firebase.core.FlutterFirebaseCorePlugin'),
    );
    expect(
      eagerPlugins,
      contains(
        'io.flutter.plugins.firebase.messaging.'
        'FlutterFirebaseMessagingPlugin',
      ),
    );
    expect(
      eagerPlugins,
      contains('io.flutter.plugins.sharedpreferences.SharedPreferencesPlugin'),
    );
    expect(
      deferredRtcPlugins,
      isNot(
        contains(
          'com.hiennv.flutter_callkit_incoming.'
          'FlutterCallkitIncomingPlugin',
        ),
      ),
    );
    expect(
      pluginPolicy,
      contains('"io.flutter.plugins.firebase.core.FlutterFirebaseCorePlugin"'),
    );
    expect(
      pluginPolicy,
      contains(
        '"io.flutter.plugins.firebase.messaging.'
        'FlutterFirebaseMessagingPlugin"',
      ),
    );
    expect(deferredRegistry, isNot(contains('FlutterCallkitIncomingPlugin')));
    expect(deferredRegistry, isNot(contains('SharedPreferencesPlugin')));
    expect(eagerRegistry, contains('FlutterCallkitIncomingPlugin'));
    expect(eagerRegistry, contains('SharedPreferencesPlugin'));
    expect(eagerRegistry, isNot(contains('FlutterWebRTCPlugin')));
    expect(firebaseRuntime, contains("@pragma('vm:entry-point')"));
    expect(firebaseRuntime, contains('onBackgroundMessage'));
    expect(firebaseRuntime, contains('canUseFullScreenIntent'));
    expect(firebaseRuntime, contains('IncomingCallPushEnvelope.fromMap'));
    expect(firebaseRuntime, contains('IncomingCallPushAction.cancel'));
    expect(
      bootstrap.indexOf('registerFirebaseIncomingCallBackgroundHandler()'),
      lessThan(bootstrap.indexOf('runApp(')),
    );
    expect(
      pushEndpointGateway,
      contains('FlutterSecurePushEndpointSecretStore'),
    );
    expect(pushEndpointGateway, isNot(contains('setString(_activeKey')));
    expect(RegExp(r'\bstartActivity\s*\(').hasMatch(firebaseRuntime), isFalse);
    expect(firebaseRuntime, isNot(contains('requestPermission')));
    expect(incomingCallPresenter, contains('isFullScreen: false'));
    expect(
      incomingCallPresenter,
      contains('isShowFullLockedScreen: fullScreenAllowed'),
    );
    expect(androidSettings, contains('id("com.google.gms.google-services")'));
    expect(androidAppBuild, contains('googleServicesConfig.isFile'));
    expect(
      androidAppBuild,
      contains('Firebase incoming calls remain fail-closed'),
    );
    expect(androidAppBuild, contains('shipsProductionBinary'));
    expect(
      androidAppBuild,
      contains(
        'production Android build requires android/app/google-services.json',
      ),
    );
    expect(androidNativeBridge, contains('"backgroundPushConfigured"'));
    expect(androidNativeBridge, contains('"google_app_id"'));
    expect(androidNativeBridge, isNot(contains('startActivity(')));
    expect(iosCallKitPlugin, contains('registeredMessengerIds'));
    expect(
      iosCallKitPlugin,
      contains('guard !registeredMessengerIds.contains(messengerId)'),
    );
    final attachedToEngineBody = RegExp(
      r'override fun onAttachedToEngine\([^\{]+\) \{(?<body>.*?)\n    \}',
      dotAll: true,
    ).firstMatch(androidCallKitPlugin)?.namedGroup('body');
    expect(attachedToEngineBody, isNotNull);
    expect(attachedToEngineBody, contains('sharePluginWithRegister'));
    expect(attachedToEngineBody, contains('schedulePhoneAccountRegistration'));
    expect(
      attachedToEngineBody,
      isNot(contains('.registerPhoneAccount()')),
      reason: 'Telecom Binder 注册不得阻塞 Flutter 主线程的 engine attach',
    );
    expect(
      androidCallKitPlugin,
      contains('phoneAccountRegistrationInFlight.compareAndSet(false, true)'),
    );
    expect(androidCallKitPlugin, contains('Executors.newSingleThreadExecutor'));
    expect(androidCallKitPlugin, contains('isDaemon = true'));
    expect(androidCallKitPlugin, contains('registrationExecutor.shutdown()'));
    expect(
      androidCallKitPlugin,
      contains('PhoneAccount registration failed off the main thread.'),
    );
  });
}
