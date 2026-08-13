// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-001
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:camera/camera.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_repository.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show circlesListQueryProvider;
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_editor_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
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
  Future<void> updateActivePersona(String personaId) async {}
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
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

class _PickerLaunchRequest {
  const _PickerLaunchRequest({
    required this.mode,
    required this.maxSelection,
    required this.initialPaths,
  });

  final MediaPickerEntryMode mode;
  final int maxSelection;
  final List<String> initialPaths;
}

class _QueuedMediaPickerLauncher {
  _QueuedMediaPickerLauncher(this._batches);

  final List<List<CreateMediaItem>> _batches;
  final List<_PickerLaunchRequest> requests = <_PickerLaunchRequest>[];
  int _callCount = 0;

  Future<CreateMediaPickerResult?> call(
    BuildContext context, {
    required MediaPickerEntryMode mode,
    required int maxSelection,
    List<String> initialPaths = const <String>[],
  }) async {
    requests.add(
      _PickerLaunchRequest(
        mode: mode,
        maxSelection: maxSelection,
        initialPaths: List<String>.from(initialPaths),
      ),
    );
    final batchIndex = _callCount;
    _callCount += 1;
    final items = batchIndex < _batches.length
        ? _batches[batchIndex]
        : const <CreateMediaItem>[];
    return Navigator.of(context).push<CreateMediaPickerResult>(
      CupertinoPageRoute<CreateMediaPickerResult>(
        builder: (_) =>
            _FakeMediaPickerPage(step: batchIndex + 1, items: items),
      ),
    );
  }
}

class _FakeMediaPickerPage extends StatelessWidget {
  const _FakeMediaPickerPage({required this.step, required this.items});

  final int step;
  final List<CreateMediaItem> items;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: Colors.black,
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          '模拟图片选择器 $step',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.black,
      ),
      child: Center(
        child: CupertinoButton.filled(
          key: ValueKey<String>('fake-picker-confirm-$step'),
          onPressed: () =>
              Navigator.of(context).pop(CreateMediaPickerResult(items: items)),
          child: const Text('确认选择'),
        ),
      ),
    );
  }
}

Widget _buildApp(_QueuedMediaPickerLauncher launcher) {
  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      circlesListQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(
        _AuthenticatedSessionController.new,
      ),
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
          initialTabKey: 'photo',
          mediaPickerLauncher: launcher.call,
        ),
      ),
    ),
  );
}

CreateMediaItem _imageItem(String id) {
  return CreateMediaItem(
    id: id,
    path: '/tmp/$id.jpg',
    type: CreateMediaType.image,
    source: CreateMediaSource.album,
  );
}

const _fakeBackAndFrontCameras = <CameraDescription>[
  CameraDescription(
    name: 'back',
    lensDirection: CameraLensDirection.back,
    sensorOrientation: 90,
  ),
  CameraDescription(
    name: 'front',
    lensDirection: CameraLensDirection.front,
    sensorOrientation: 270,
  ),
];

Widget _fakePreview(BuildContext context) {
  return const ColoredBox(color: CupertinoColors.black);
}

Future<String> _fakeCapture() async => '/tmp/captured.jpg';

Future<String?> _fakeCreateEditor(
  BuildContext context,
  CameraPhotoEditorRequest request,
) async {
  expect(request.caller, CameraPhotoCaller.create);
  expect(request.entrySource, CameraPhotoEntrySource.publishEntry);
  return '/tmp/create-camera-edited.jpg';
}

class _FakeFilterRepository extends ImageEditorFilterRepository {
  @override
  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets() async {
    return const <ImageEditorFilterPreset>[
      ImageEditorFilterPreset(
        id: 'original',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: MediaText.imageEditOriginal,
        sort: 1,
        enabled: true,
        defaultStrength: 0,
        adjustments: ImageEditorFilterAdjustments(),
      ),
    ];
  }
}

void _usePhoneSurface(WidgetTester tester) {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    AppPermissionCoordinator.instance.ensureLifecycleAttached();
    AppPermissionCoordinator.instance.phaseReaders[AppPermissionKind.photos] =
        () async => AppPermissionPhase.granted;
    AppPermissionCoordinator.instance.grantCheckers[AppPermissionKind.photos] =
        () async => true;
    AppPermissionCoordinator.instance.requesters[AppPermissionKind.photos] =
        () async => true;
  });

  tearDown(() {
    AppPermissionCoordinator.instance.phaseReaders.remove(
      AppPermissionKind.photos,
    );
    AppPermissionCoordinator.instance.grantCheckers.remove(
      AppPermissionKind.photos,
    );
    AppPermissionCoordinator.instance.requesters.remove(
      AppPermissionKind.photos,
    );
    AppPermissionCoordinator.instance.clearSession();
  });

  testWidgets('创作页重入图片选择器时新图片追加到原列表末尾', (tester) async {
    final launcher = _QueuedMediaPickerLauncher(<List<CreateMediaItem>>[
      <CreateMediaItem>[_imageItem('first')],
      <CreateMediaItem>[_imageItem('second')],
    ]);

    await tester.pumpWidget(_buildApp(launcher));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage, skipOffstage: false)),
    );

    await tester.ensureVisible(find.byKey(TestKeys.createMediaAddButton));
    await tester.tap(find.byKey(TestKeys.createMediaAddButton));
    await tester.pumpAndSettle();

    expect(find.text('模拟图片选择器 1'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey<String>('fake-picker-confirm-1')),
    );
    await tester.pumpAndSettle();

    expect(container.read(createEditorProvider).imagePaths, <String>[
      '/tmp/first.jpg',
    ]);

    await tester.ensureVisible(find.byKey(TestKeys.createMediaAddButton));
    await tester.tap(find.byKey(TestKeys.createMediaAddButton));
    await tester.pumpAndSettle();

    expect(find.text('模拟图片选择器 2'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey<String>('fake-picker-confirm-2')),
    );
    await tester.pumpAndSettle();

    expect(container.read(createEditorProvider).imagePaths, <String>[
      '/tmp/first.jpg',
      '/tmp/second.jpg',
    ]);
    expect(
      launcher.requests.map((request) => request.mode).toList(),
      <MediaPickerEntryMode>[
        MediaPickerEntryMode.image,
        MediaPickerEntryMode.image,
      ],
    );
    expect(
      launcher.requests.map((request) => request.maxSelection).toList(),
      <int>[20, 19],
    );
    expect(
      launcher.requests.every((request) => request.initialPaths.isEmpty),
      isTrue,
    );
  });

  testWidgets('/create?type=capture&tab=photo 可显式直达拍照编辑后追加到创作页图片列表', (
    tester,
  ) async {
    _usePhoneSurface(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentUserIdProvider.overrideWithValue('user_001'),
          ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
          circlesListQueryProvider.overrideWithValue(
            InMemoryCircleQueryReader(),
          ),
          authSessionStoreProvider.overrideWithValue(
            const _AuthedSessionStore(),
          ),
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
              initialAction: EditorStartAction.capture,
              initialTabKey: 'photo',
              cameraPageBuilder:
                  (
                    context, {
                    required initialMode,
                    required caller,
                    required entrySource,
                    required selectedCountBeforeCapture,
                  }) => CameraCapturePage(
                    initialMode: initialMode,
                    allowVideoMode: false,
                    caller: caller,
                    entrySource: entrySource,
                    selectedCountBeforeCapture: selectedCountBeforeCapture,
                    previewBuilder: _fakePreview,
                    previewCameraDescriptions: _fakeBackAndFrontCameras,
                    filterRepository: _FakeFilterRepository(),
                    photoCapture: _fakeCapture,
                    imageEditorLauncher: _fakeCreateEditor,
                  ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage, skipOffstage: false)),
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(MediaText.cameraUsePhoto));
    await tester.pumpAndSettle();

    expect(container.read(createEditorProvider).imagePaths, <String>[
      '/tmp/create-camera-edited.jpg',
    ]);
  });
}
