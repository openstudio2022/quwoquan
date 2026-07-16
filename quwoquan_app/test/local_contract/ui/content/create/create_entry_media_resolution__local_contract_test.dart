import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/video_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('media result uses the first media type as route resolution', () {
    final imageA = _item('image_a', CreateMediaType.image);
    final imageB = _item('image_b', CreateMediaType.image);
    final video = _item('video_a', CreateMediaType.video);

    expect(
      resolveCreateEntryMediaResolution(const <CreateMediaItem>[]),
      CreateEntryMediaResolution.empty,
    );
    expect(
      resolveCreateEntryMediaResolution(<CreateMediaItem>[imageA, imageB]),
      CreateEntryMediaResolution.imageBatch,
    );
    expect(
      resolveCreateEntryMediaResolution(<CreateMediaItem>[video]),
      CreateEntryMediaResolution.video,
    );
    expect(
      resolveCreateEntryMediaResolution(<CreateMediaItem>[imageA, video]),
      CreateEntryMediaResolution.imageBatch,
    );
  });

  testWidgets('photo entry image result enters image media editor state', (
    tester,
  ) async {
    final requestedModes = <MediaPickerEntryMode>[];

    await tester.pumpWidget(
      _buildHarness(
        initialAction: EditorStartAction.gallery,
        mediaPickerLauncher:
            (
              context, {
              required mode,
              required maxSelection,
              List<String> initialPaths = const <String>[],
            }) async {
              requestedModes.add(mode);
              return CreateMediaPickerResult(
                items: <CreateMediaItem>[
                  _item('image_a', CreateMediaType.image),
                  _item('image_b', CreateMediaType.image),
                ],
              );
            },
      ),
    );
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final state = container.read(createEditorProvider);

    expect(requestedModes, <MediaPickerEntryMode>[MediaPickerEntryMode.image]);
    expect(state.editorKind, CreateEditorKind.media);
    expect(state.draftFlowKind, CreateDraftFlowKind.image);
    expect(state.mediaKind, CreateMediaKind.images);
    expect(state.imagePaths, <String>['/tmp/image_a', '/tmp/image_b']);
    expect(state.videoPath, isEmpty);
  });

  testWidgets(
    'one tap original result enters locked image media state without native movie',
    (tester) async {
      await tester.pumpWidget(
        _buildHarness(
          initialAction: EditorStartAction.gallery,
          mediaPickerLauncher:
              (
                context, {
                required mode,
                required maxSelection,
                List<String> initialPaths = const <String>[],
              }) async {
                return CreateMediaPickerResult(
                  openOneTapMovie: true,
                  lockedSingleMedia: true,
                  oneTapMovieEffectId: 'original',
                  items: <CreateMediaItem>[
                    _item('image_a', CreateMediaType.image),
                    _item('image_b', CreateMediaType.image),
                  ],
                );
              },
        ),
      );
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(CreatePage)),
      );
      final state = container.read(createEditorProvider);

      expect(state.editorKind, CreateEditorKind.media);
      expect(state.draftFlowKind, CreateDraftFlowKind.image);
      expect(state.mediaKind, CreateMediaKind.images);
      expect(state.imagePaths, <String>['/tmp/image_a']);
      expect(state.isOneTapMovie, isTrue);
      expect(state.oneTapMoviePath, isEmpty);
      expect(state.oneTapMovieEffectId, 'original');
      expect(state.videoPath, isEmpty);
    },
  );

  testWidgets(
    'video entry video result enters video editor then video media state',
    (tester) async {
      final requestedModes = <MediaPickerEntryMode>[];
      final preparedPaths = <String>[];
      var videoEditorCalls = 0;

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
                return CreateMediaPickerResult(
                  items: <CreateMediaItem>[
                    _item('video_a', CreateMediaType.video),
                  ],
                );
              },
          videoPreparationProbe: (path) async {
            preparedPaths.add(path);
            return const CreateVideoPreparationResult(
              durationMs: 9000,
              thumbnailPath: '/tmp/video_cover.jpg',
              width: 1080,
              height: 1920,
            );
          },
          videoEditorLauncher: (context, {required state}) async {
            videoEditorCalls += 1;
            expect(state.draftFlowKind, CreateDraftFlowKind.video);
            expect(state.mediaKind, CreateMediaKind.video);
            expect(state.videoPath, '/tmp/video_a');
            expect(state.imagePaths, isEmpty);
            return const VideoEditorResult(
              videoPath: '/tmp/video_edited.mp4',
              originalVideoPath: '/tmp/video_a',
              thumbnailPath: '/tmp/video_cover_edited.jpg',
              durationMs: 8000,
              trimStartMs: 500,
              trimEndMs: 8500,
              coverTimeMs: 1500,
              coverStrategy: 'manual',
              width: 1080,
              height: 1920,
              muted: true,
            );
          },
        ),
      );
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(CreatePage)),
      );
      final state = container.read(createEditorProvider);

      expect(requestedModes, <MediaPickerEntryMode>[
        MediaPickerEntryMode.video,
      ]);
      expect(preparedPaths, <String>['/tmp/video_a']);
      expect(videoEditorCalls, 1);
      expect(state.editorKind, CreateEditorKind.media);
      expect(state.draftFlowKind, CreateDraftFlowKind.video);
      expect(state.mediaKind, CreateMediaKind.video);
      expect(state.videoPath, '/tmp/video_edited.mp4');
      expect(state.originalVideoPath, '/tmp/video_a');
      expect(state.videoThumbnail, '/tmp/video_cover_edited.jpg');
      expect(state.videoDurationMs, 8000);
      expect(state.videoTrimStartMs, 500);
      expect(state.videoTrimEndMs, 8500);
      expect(state.videoCoverTimeMs, 1500);
      expect(state.videoMuted, isTrue);
      expect(state.imagePaths, isEmpty);
    },
  );
}

CreateMediaItem _item(String id, CreateMediaType type) {
  return CreateMediaItem(
    id: id,
    path: '/tmp/$id',
    type: type,
    source: CreateMediaSource.album,
  );
}

Widget _buildHarness({
  EditorStartAction? initialAction,
  CreateMediaPickerLauncher? mediaPickerLauncher,
  CreateVideoPreparationProbe? videoPreparationProbe,
  CreateVideoEditorLauncher? videoEditorLauncher,
}) {
  return ProviderScope(
    overrides: [
      currentUserIdProvider.overrideWithValue('user_001'),
      startupAuthRestoreGateProvider.overrideWith(() => _OpenStartupAuthGate()),
      ...mockContentFacetOverrides(MockContentRepository()),
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
          initialAction: initialAction,
          mediaPickerLauncher: mediaPickerLauncher,
          videoPreparationProbe: videoPreparationProbe,
          videoEditorLauncher: videoEditorLauncher,
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
  Future<void> saveRefreshedAccountHint(
    Map<String, dynamic>? accountHint,
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
