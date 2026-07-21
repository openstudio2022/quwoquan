import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('照片入口打开图片选择器', (tester) async {
    final requestedModes = <MediaPickerEntryMode>[];
    await tester.pumpWidget(
      _buildHarness(
        initialAction: EditorStartAction.gallery,
        initialTabKey: 'video',
        mediaPickerLauncher:
            (
              context, {
              required mode,
              required maxSelection,
              List<String> initialPaths = const <String>[],
            }) async {
              requestedModes.add(mode);
              return null;
            },
      ),
    );
    await tester.pumpAndSettle();

    expect(requestedModes, <MediaPickerEntryMode>[MediaPickerEntryMode.image]);
  });

  testWidgets('视频入口打开视频选择器', (tester) async {
    final requestedModes = <MediaPickerEntryMode>[];
    await tester.pumpWidget(
      _buildHarness(
        initialAction: EditorStartAction.video,
        mediaPickerLauncher:
            (
              context, {
              required mode,
              required maxSelection,
              List<String> initialPaths = const <String>[],
            }) async {
              requestedModes.add(mode);
              return null;
            },
      ),
    );
    await tester.pumpAndSettle();

    expect(requestedModes, <MediaPickerEntryMode>[MediaPickerEntryMode.video]);
  });

  testWidgets('老相机入口默认拍照，由相机页负责切到录像', (tester) async {
    MediaPickerEntryMode? openedMode;
    await tester.pumpWidget(
      _buildHarness(
        initialAction: EditorStartAction.capture,
        cameraPageBuilder:
            (
              context, {
              required initialMode,
              required caller,
              required entrySource,
              required selectedCountBeforeCapture,
            }) {
              openedMode = initialMode;
              return CupertinoPageScaffold(
                child: Center(
                  child: Text(
                    initialMode == MediaPickerEntryMode.video
                        ? 'video-camera'
                        : 'image-camera',
                  ),
                ),
              );
            },
      ),
    );
    await tester.pumpAndSettle();

    expect(openedMode, MediaPickerEntryMode.image);
    expect(find.text('image-camera'), findsOneWidget);
    expect(find.text('video-camera'), findsNothing);
  });
}

Widget _buildHarness({
  String? initialTabKey,
  EditorStartAction? initialAction,
  CreateMediaPickerLauncher? mediaPickerLauncher,
  CreateCameraPageBuilder? cameraPageBuilder,
}) {
  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      startupAuthRestoreGateProvider.overrideWith(() => _OpenStartupAuthGate()),
      ...mockContentFacetOverrides(MockContentRepository()),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            _AuthWarmup(child: child ?? const SizedBox.shrink()),
        home: CreatePage(
          initialTabKey: initialTabKey,
          initialAction: initialAction,
          mediaPickerLauncher: mediaPickerLauncher,
          cameraPageBuilder: cameraPageBuilder,
        ),
      ),
    ),
  );
}

class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activeSubAccountId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}
}

class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}
