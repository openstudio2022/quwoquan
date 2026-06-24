library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:camera/camera.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/camera/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

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
            _FakeMediaPickerJourneyPage(step: batchIndex + 1, items: items),
      ),
    );
  }
}

class _FakeMediaPickerJourneyPage extends StatelessWidget {
  const _FakeMediaPickerJourneyPage({required this.step, required this.items});

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
      contentRepositoryProvider.overrideWithValue(MockContentRepository()),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
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

Future<String?> _fakePickerEditor(
  BuildContext context,
  CameraPhotoEditorRequest request,
) async {
  expect(request.caller, CameraPhotoCaller.picker);
  expect(request.entrySource, CameraPhotoEntrySource.photoPicker);
  return '/tmp/picker-camera-edited.jpg';
}

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
        name: UITextConstants.imageEditOriginal,
        sort: 1,
        enabled: true,
        defaultStrength: 0,
        params: <String, double>{},
      ),
    ];
  }
}

class _EmptyMediaPickerService extends MediaPickerService {
  @override
  Future<bool> ensurePhotoPermission() async => true;

  @override
  Future<List<AssetPathEntity>> loadAlbums({required RequestType type}) async {
    return <AssetPathEntity>[
      AssetPathEntity(id: 'recent', name: '最近项目', type: RequestType.image),
    ];
  }

  @override
  Future<List<AssetEntity>> loadAssets({
    required AssetPathEntity album,
    required int page,
    required int pageSize,
  }) async {
    return const <AssetEntity>[];
  }

  @override
  Future<int> loadAlbumAssetCount(AssetPathEntity album) async => 0;
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

  testWidgets('图片选择器首格拍照会进入编辑器并回 picker 追加', (tester) async {
    _usePhoneSurface(tester);
    CreateMediaPickerResult? result;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open picker'),
            onPressed: () async {
              result = await Navigator.of(context)
                  .push<CreateMediaPickerResult>(
                    CupertinoPageRoute<CreateMediaPickerResult>(
                      builder: (_) => CreateMediaPickerPage(
                        entryMode: MediaPickerEntryMode.image,
                        maxSelection: 9,
                        mediaPickerService: _EmptyMediaPickerService(),
                        cameraBuilder:
                            (
                              context,
                              caller,
                              entrySource,
                              selectedCountBeforeCapture,
                            ) => CameraCapturePage(
                              initialMode: MediaPickerEntryMode.image,
                              allowVideoMode: false,
                              caller: caller,
                              entrySource: entrySource,
                              selectedCountBeforeCapture:
                                  selectedCountBeforeCapture,
                              previewBuilder: _fakePreview,
                              previewCameraDescriptions:
                                  _fakeBackAndFrontCameras,
                              filterRepository: _FakeFilterRepository(),
                              photoCapture: _fakeCapture,
                              imageEditorLauncher: _fakePickerEditor,
                            ),
                      ),
                    ),
                  );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open picker'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('media-picker-camera-tile')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.cameraUsePhoto));
    await tester.pumpAndSettle();
    await tester.tap(find.text('完成(1)'));
    await tester.pumpAndSettle();

    expect(result?.items.map((item) => item.path), <String>[
      '/tmp/picker-camera-edited.jpg',
    ]);
  });

  testWidgets('/create?type=capture&tab=photo 可显式直达拍照编辑后追加到创作页图片列表', (tester) async {
    _usePhoneSurface(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentUserIdProvider.overrideWithValue('user_001'),
          contentRepositoryProvider.overrideWithValue(MockContentRepository()),
          circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
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
    await tester.tap(find.text(UITextConstants.cameraUsePhoto));
    await tester.pumpAndSettle();

    expect(container.read(createEditorProvider).imagePaths, <String>[
      '/tmp/create-camera-edited.jpg',
    ]);
  });
}
