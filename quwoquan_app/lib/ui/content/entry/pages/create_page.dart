import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:video_thumbnail/video_thumbnail.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_preview_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_circle_select_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/video_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';

class CreatePage extends ConsumerStatefulWidget {
  const CreatePage({
    super.key,
    this.initialAction,
    this.initialTabKey,
    this.initialHomepage,
  });

  final EditorStartAction? initialAction;
  final String? initialTabKey;
  final HomepageCanonicalReference? initialHomepage;

  @override
  ConsumerState<CreatePage> createState() => _CreatePageState();
}

class _CreatePageState extends ConsumerState<CreatePage> {
  static const String _draftsStorageKey = 'create_drafts_list';
  static const String _currentDraftIdKey = 'create_current_draft_id';
  static const int _kMaxMediaImages = 20;
  static const int _kMaxBodyLength = 5000;

  final CreateLocationService _locationService = CreateLocationService();
  final CreateCircleService _circleService = const CreateCircleService();
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _bodyController = TextEditingController();
  final FocusNode _titleFocusNode = FocusNode();
  final FocusNode _bodyFocusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();

  Timer? _autoSaveTimer;
  bool _didApplyInitialAction = false;
  bool _isPublishing = false;
  double _heroCollapseProgress = 0;
  String? _draggingMediaPath;
  String? _pressedMediaPath;
  List<CreateDraft> _savedDrafts = <CreateDraft>[];
  String? _currentDraftId;

  bool get _editorV2Enabled =>
      ref.read(contentFeatureFlagProvider('create_editor_v2')) ||
      ref.read(contentFeatureFlagProvider('enable_unified_create_editor'));

  bool _useImmersiveArticleExperience(CreateEditorStateV2 state) {
    return widget.initialAction == EditorStartAction.write &&
        state.editorKind == CreateEditorKind.text;
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
    _loadDrafts();
    _autoSaveTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      final state = ref.read(createEditorProvider);
      if (state.hasContent) {
        unawaited(_saveDraft(silent: true));
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) {
        return;
      }
      final notifier = ref.read(createEditorProvider.notifier);
      notifier.reset(editorKind: _resolveInitialEditorKind());
      if (widget.initialAction != null) {
        notifier.setStartAction(widget.initialAction);
      }
      if (widget.initialHomepage != null) {
        notifier.setSettings(
          ref
              .read(createEditorProvider)
              .settings
              .copyWith(homepage: widget.initialHomepage),
        );
      }
      _syncControllersFromState(ref.read(createEditorProvider));
      await _applyInitialActionIfNeeded();
      await _reportEvent('create_editor_ready', <String, dynamic>{
        'editorKind': ref.read(createEditorProvider).editorKind.name,
        'flag': _editorV2Enabled,
      });
    });
  }

  @override
  void dispose() {
    _autoSaveTimer?.cancel();
    _scrollController
      ..removeListener(_handleScroll)
      ..dispose();
    _titleController.dispose();
    _bodyController.dispose();
    _titleFocusNode.dispose();
    _bodyFocusNode.dispose();
    super.dispose();
  }

  void _handleScroll() {
    final next =
        (_scrollController.hasClients ? _scrollController.offset / 96 : 0.0)
            .clamp(0.0, 1.0)
            .toDouble();
    if ((next - _heroCollapseProgress).abs() < 0.02 || !mounted) {
      return;
    }
    setState(() {
      _heroCollapseProgress = next;
    });
  }

  CreateEditorKind _resolveInitialEditorKind() {
    if (widget.initialAction == EditorStartAction.gallery ||
        widget.initialAction == EditorStartAction.capture) {
      return CreateEditorKind.media;
    }
    switch ((widget.initialTabKey ?? '').trim()) {
      case 'photo':
      case 'video':
        return CreateEditorKind.media;
      default:
        return CreateEditorKind.text;
    }
  }

  Future<void> _applyInitialActionIfNeeded() async {
    if (_didApplyInitialAction) {
      return;
    }
    _didApplyInitialAction = true;
    switch (widget.initialAction) {
      case EditorStartAction.gallery:
        await _pickImagesForCurrentEditor();
        return;
      case EditorStartAction.capture:
        await _openCameraForCurrentEditor();
        return;
      case EditorStartAction.write:
      case null:
        _focusBodyField();
        return;
    }
  }

  void _syncControllersFromState(CreateEditorStateV2 state) {
    if (_titleController.text != state.title) {
      _titleController.value = TextEditingValue(
        text: state.title,
        selection: TextSelection.collapsed(offset: state.title.length),
      );
    }
    if (_bodyController.text != state.body) {
      _bodyController.value = TextEditingValue(
        text: state.body,
        selection: TextSelection.collapsed(offset: state.body.length),
      );
    }
  }

  void _focusBodyField() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final state = ref.read(createEditorProvider);
      if (state.editorKind == CreateEditorKind.text) {
        ref
            .read(createEditorProvider.notifier)
            .setActiveArticlePage(state.articlePages.first.id);
        return;
      }
      _bodyFocusNode.requestFocus();
    });
  }

  void _focusTitleField() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _titleFocusNode.requestFocus();
      }
    });
  }

  String _coverAssetPathForState(CreateEditorStateV2 state) {
    if (state.editorKind == CreateEditorKind.text) {
      return _shouldPublishAsArticle(state)
          ? state.articleCoverImagePath.trim()
          : '';
    }
    if (state.hasVideo) {
      if (state.videoThumbnail.trim().isNotEmpty) {
        return state.videoThumbnail.trim();
      }
      return state.videoPath.trim();
    }
    if (state.imagePaths.isEmpty) {
      return '';
    }
    return state.imagePaths.first;
  }

  int _mediaColumnsForWidth(double width) {
    if (width >= 720) {
      return 5;
    }
    if (width >= 520) {
      return 4;
    }
    return 3;
  }

  double _mediaTileAspectRatioForColumns(int columns) {
    switch (columns) {
      case 4:
        return 1.08;
      case 3:
        return 1.12;
      default:
        return 1.16;
    }
  }

  String _pageTitleForState(CreateEditorStateV2 state) {
    return '创作';
  }

  String _mediaHeaderHintForState(CreateEditorStateV2 state) {
    if (state.hasVideo) {
      return '轻点视频编辑，可设置封面';
    }
    if (state.imagePaths.isEmpty) {
      return '先添加图片或视频';
    }
    return '拖拽排序，轻点编辑';
  }

  bool _canAddMoreImages(CreateEditorStateV2 state) {
    return !state.hasVideo && state.imagePaths.length < _kMaxMediaImages;
  }

  void _autoScrollDuringMediaDrag(Offset globalPosition) {
    if (!_scrollController.hasClients || !mounted) {
      return;
    }
    final overlay = Overlay.maybeOf(context);
    final renderBox = overlay?.context.findRenderObject() as RenderBox?;
    if (renderBox == null) {
      return;
    }
    final local = renderBox.globalToLocal(globalPosition);
    final viewportHeight = MediaQuery.sizeOf(context).height;
    final topBoundary =
        MediaQuery.paddingOf(context).top + AppSpacing.toolbarHeight;
    final bottomBoundary =
        viewportHeight - MediaQuery.paddingOf(context).bottom;
    const edgeThreshold = 96.0;
    const maxDelta = 18.0;

    double delta = 0;
    if (local.dy < topBoundary + edgeThreshold) {
      final ratio = ((topBoundary + edgeThreshold - local.dy) / edgeThreshold)
          .clamp(0.0, 1.0);
      delta = -maxDelta * ratio;
    } else if (local.dy > bottomBoundary - edgeThreshold) {
      final ratio =
          ((local.dy - (bottomBoundary - edgeThreshold)) / edgeThreshold).clamp(
            0.0,
            1.0,
          );
      delta = maxDelta * ratio;
    }

    if (delta.abs() < 0.5) {
      return;
    }

    final nextOffset = (_scrollController.offset + delta).clamp(
      0.0,
      _scrollController.position.maxScrollExtent,
    );
    if ((nextOffset - _scrollController.offset).abs() < 0.1) {
      return;
    }
    _scrollController.jumpTo(nextOffset);
  }

  void _reorderImageByPath(String draggedPath, int targetIndex) {
    final state = ref.read(createEditorProvider);
    final fromIndex = state.imagePaths.indexOf(draggedPath);
    if (fromIndex < 0 || fromIndex == targetIndex) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .reorderImages(fromIndex, targetIndex);
  }

  Future<void> _reportEvent(
    String event, [
    Map<String, dynamic> extras = const <String, dynamic>{},
  ]) async {
    try {
      await ref
          .read(contentRepositoryProvider)
          .reportBehaviors(
            events: <Map<String, dynamic>>[
              <String, dynamic>{
                'event': event,
                'surface': 'create_editor',
                'timestamp': DateTime.now().toIso8601String(),
                ...extras,
              },
            ],
          );
    } catch (_) {
      // Keep editor resilient when reporting fails.
    }
  }

  Future<void> _loadDrafts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_draftsStorageKey);
    if (raw == null || raw.isEmpty) {
      return;
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return;
      }
      final drafts = decoded
          .whereType<Map>()
          .map(
            (entry) =>
                CreateDraft.fromStorageMap(Map<String, dynamic>.from(entry)),
          )
          .toList(growable: false);
      if (!mounted) {
        return;
      }
      setState(() {
        _savedDrafts = drafts;
      });
      _currentDraftId = prefs.getString(_currentDraftIdKey);
    } catch (_) {
      // Ignore malformed drafts cache.
    }
  }

  Future<void> _persistDrafts(
    List<CreateDraft> drafts,
    String? currentId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _draftsStorageKey,
      jsonEncode(
        drafts.map((draft) => draft.toStorageMap()).toList(growable: false),
      ),
    );
    if (currentId == null) {
      await prefs.remove(_currentDraftIdKey);
    } else {
      await prefs.setString(_currentDraftIdKey, currentId);
    }
  }

  Future<void> _saveDraft({bool silent = false}) async {
    final state = ref.read(createEditorProvider);
    if (!state.hasContent) {
      return;
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    final nextId = _currentDraftId ?? state.draftId ?? 'draft_$now';
    final nextDraft = CreateDraft(
      id: nextId,
      updatedAtMs: now,
      state: state.copyWith(draftId: nextId),
    );
    final nextDrafts = <CreateDraft>[
      nextDraft,
      ..._savedDrafts.where((draft) => draft.id != nextId),
    ];
    setState(() {
      _savedDrafts = nextDrafts;
      _currentDraftId = nextId;
    });
    ref.read(createEditorProvider.notifier).setDraftId(nextId);
    await _persistDrafts(nextDrafts, nextId);
    await _reportEvent('create_draft_saved', <String, dynamic>{
      'editorKind': nextDraft.state.editorKind.name,
    });
    if (!silent && mounted) {
      AppToast.show(context, UITextConstants.saveDraft);
    }
  }

  Future<void> _clearCurrentDraft() async {
    if (_currentDraftId == null) {
      return;
    }
    final nextDrafts = _savedDrafts
        .where((draft) => draft.id != _currentDraftId)
        .toList(growable: false);
    setState(() {
      _savedDrafts = nextDrafts;
      _currentDraftId = null;
    });
    ref.read(createEditorProvider.notifier).setDraftId(null);
    await _persistDrafts(nextDrafts, null);
  }

  Future<void> _restoreDraft(CreateDraft draft) async {
    ref.read(createEditorProvider.notifier).restoreFromDraft(draft);
    _syncControllersFromState(draft.state);
    setState(() {
      _currentDraftId = draft.id;
    });
    await _persistDrafts(_savedDrafts, draft.id);
    await _reportEvent('create_draft_restored', <String, dynamic>{
      'editorKind': draft.state.editorKind.name,
    });
    if (draft.state.editorKind == CreateEditorKind.text) {
      _focusBodyField();
    }
  }

  Future<void> _deleteDraft(String draftId) async {
    final nextDrafts = _savedDrafts
        .where((draft) => draft.id != draftId)
        .toList(growable: false);
    final nextCurrentId = _currentDraftId == draftId ? null : _currentDraftId;
    setState(() {
      _savedDrafts = nextDrafts;
      _currentDraftId = nextCurrentId;
    });
    if (nextCurrentId == null) {
      ref.read(createEditorProvider.notifier).setDraftId(null);
    }
    await _persistDrafts(nextDrafts, nextCurrentId);
  }

  Future<void> _showDraftsSheet() async {
    if (_savedDrafts.isEmpty) {
      return;
    }
    await showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (sheetContext) {
        return _CreateDraftsSheet(
          drafts: _savedDrafts,
          onSelect: (draft) async {
            Navigator.of(sheetContext).pop();
            await _restoreDraft(draft);
          },
          onDelete: (draft) async {
            await _deleteDraft(draft.id);
            if (sheetContext.mounted && _savedDrafts.isEmpty) {
              Navigator.of(sheetContext).pop();
            }
          },
        );
      },
    );
  }

  Future<void> _onCloseRequest() async {
    final state = ref.read(createEditorProvider);
    if (!state.hasContent) {
      _doClose();
      return;
    }
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.createExitConfirmTitle),
          content: const Text(UITextConstants.createExitConfirmDesc),
          actions: <Widget>[
            CupertinoDialogAction(
              key: TestKeys.createDiscardAndExitButton,
              isDestructiveAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _clearCurrentDraft();
                _doClose();
              },
              child: const Text(UITextConstants.discard),
            ),
            CupertinoDialogAction(
              key: TestKeys.createSaveAndExitButton,
              isDefaultAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _saveDraft();
                _doClose();
              },
              child: const Text(UITextConstants.saveDraft),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(UITextConstants.cancel),
            ),
          ],
        );
      },
    );
  }

  void _doClose() {
    final navigator = Navigator.maybeOf(context);
    if (navigator != null && navigator.canPop()) {
      navigator.pop();
      return;
    }
    try {
      context.go(AppRoutePaths.home);
    } catch (_) {
      // Widget tests may not mount a GoRouter.
    }
  }

  Future<CreateMediaPickerResult?> _openMediaPicker({
    required MediaPickerEntryMode mode,
    required int maxSelection,
    List<String> initialPaths = const <String>[],
  }) {
    final initialSelection = initialPaths
        .map(
          (path) => CreateMediaItem(
            id: path,
            path: path,
            type: mode == MediaPickerEntryMode.video
                ? CreateMediaType.video
                : CreateMediaType.image,
            source: CreateMediaSource.album,
          ),
        )
        .toList(growable: false);
    return Navigator.of(context).push<CreateMediaPickerResult>(
      MaterialPageRoute<CreateMediaPickerResult>(
        fullscreenDialog: true,
        builder: (_) => CreateMediaPickerPage(
          entryMode: mode,
          maxSelection: maxSelection,
          initialSelection: initialSelection,
        ),
      ),
    );
  }

  Future<void> _pickImagesForCurrentEditor() async {
    final state = ref.read(createEditorProvider);
    if (state.hasVideo && state.editorKind == CreateEditorKind.media) {
      AppToast.show(context, '请先删除当前视频，再改为图片');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: _kMaxMediaImages,
      initialPaths: state.imagePaths,
    );
    if (!mounted || result == null) {
      return;
    }
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(_kMaxMediaImages)
        .toList(growable: false);
    if (state.editorKind == CreateEditorKind.text) {
      final notifier = ref.read(createEditorProvider.notifier);
      final activePageId =
          state.activeArticlePageId ?? state.articlePages.first.id;
      if (paths.isNotEmpty) {
        notifier.replaceArticlePageImage(activePageId, paths.first);
      }
      var anchorPageId = activePageId;
      for (final path in paths.skip(1)) {
        anchorPageId = notifier.insertArticleImageAfterPage(anchorPageId, path);
      }
      await _reportEvent('create_media_images_selected', <String, dynamic>{
        'count': paths.length,
        'editorKind': state.editorKind.name,
      });
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .setImages(paths, editorKind: state.editorKind);
    await _reportEvent('create_media_images_selected', <String, dynamic>{
      'count': paths.length,
      'editorKind': state.editorKind.name,
    });
  }

  Future<void> _pickVideoForMedia() async {
    final state = ref.read(createEditorProvider);
    if (state.imagePaths.isNotEmpty) {
      AppToast.show(context, '请先删空图片，再改为视频');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.video,
      maxSelection: 1,
      initialPaths: state.videoPath.trim().isEmpty
          ? const <String>[]
          : <String>[state.videoPath],
    );
    if (!mounted || result == null || result.items.isEmpty) {
      return;
    }
    final item = result.items.first;
    final thumbnail = await _generateVideoThumbnail(item.path);
    final durationMs = await _loadVideoDurationMs(item.path);
    final preserved = _deriveVideoEditContext(
      previousState: state,
      nextDurationMs: durationMs,
    );
    ref
        .read(createEditorProvider.notifier)
        .setVideo(
          item.path,
          editorKind: CreateEditorKind.media,
          thumbnail: thumbnail ?? '',
          originalPath: item.path,
          durationMs: durationMs,
          trimStartMs: preserved.trimStartMs,
          trimEndMs: preserved.trimEndMs,
          coverTimeMs: preserved.coverTimeMs,
          muted: preserved.muted,
        );
    await _reportEvent('create_media_video_selected');
    if (state.hasVideo && mounted) {
      await _editCurrentVideo();
    }
  }

  Future<void> _openCameraForCurrentEditor({
    MediaPickerEntryMode? forcedMode,
  }) async {
    final state = ref.read(createEditorProvider);
    final initialMode =
        forcedMode ??
        (state.editorKind == CreateEditorKind.media &&
                state.mediaKind == CreateMediaKind.video
            ? MediaPickerEntryMode.video
            : MediaPickerEntryMode.image);
    final result = await Navigator.of(context).push<CameraCaptureResult>(
      MaterialPageRoute<CameraCaptureResult>(
        fullscreenDialog: true,
        builder: (_) => CameraCapturePage(initialMode: initialMode),
      ),
    );
    if (!mounted || result == null) {
      return;
    }
    if (state.editorKind == CreateEditorKind.text) {
      if (result.type == CreateMediaType.video) {
        AppToast.show(context, '写文字编辑器暂不支持视频');
        return;
      }
      final activePageId =
          state.activeArticlePageId ?? state.articlePages.first.id;
      ref
          .read(createEditorProvider.notifier)
          .replaceArticlePageImage(activePageId, result.path);
      return;
    }
    if (result.type == CreateMediaType.video) {
      if (state.imagePaths.isNotEmpty) {
        AppToast.show(context, '请先删空图片，再改为视频');
        return;
      }
      final thumbnail = await _generateVideoThumbnail(result.path);
      final durationMs = await _loadVideoDurationMs(result.path);
      final preserved = _deriveVideoEditContext(
        previousState: state,
        nextDurationMs: durationMs,
      );
      ref
          .read(createEditorProvider.notifier)
          .setVideo(
            result.path,
            editorKind: CreateEditorKind.media,
            thumbnail: thumbnail ?? '',
            originalPath: result.path,
            durationMs: durationMs,
            trimStartMs: preserved.trimStartMs,
            trimEndMs: preserved.trimEndMs,
            coverTimeMs: preserved.coverTimeMs,
            muted: preserved.muted,
          );
      if (state.hasVideo && mounted) {
        await _editCurrentVideo();
      }
      return;
    }
    if (state.hasVideo) {
      AppToast.show(context, '请先删除当前视频，再改为图片');
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .appendImages(
          <String>[result.path],
          editorKind: CreateEditorKind.media,
          maxImages: _kMaxMediaImages,
        );
  }

  Future<void> _showAddMediaOptions(CreateEditorStateV2 state) async {
    final isTextEditor = state.editorKind == CreateEditorKind.text;
    final isVideoState = state.mediaKind == CreateMediaKind.video;
    final supportsVideo =
        !isTextEditor && state.imagePaths.isEmpty && !state.hasVideo;
    final action = await showAppActionSheet<_CreateMediaOption>(
      context,
      title: '添加媒体',
      sections: [
        AppActionSheetSection<_CreateMediaOption>(
          items: [
            if (!isVideoState)
              const AppActionSheetItem<_CreateMediaOption>(
                value: _CreateMediaOption.addImages,
                label: '添加图片',
                icon: CupertinoIcons.photo_on_rectangle,
              ),
            AppActionSheetItem<_CreateMediaOption>(
              value: _CreateMediaOption.capture,
              label: isVideoState ? '拍摄视频' : '拍摄',
              icon: isVideoState
                  ? CupertinoIcons.videocam
                  : CupertinoIcons.camera,
            ),
            if (supportsVideo || isVideoState)
              AppActionSheetItem<_CreateMediaOption>(
                value: _CreateMediaOption.video,
                label: isVideoState ? '更换视频' : '添加视频',
                icon: CupertinoIcons.videocam_fill,
              ),
          ],
        ),
      ],
    );
    if (!mounted || action == null) {
      return;
    }
    switch (action) {
      case _CreateMediaOption.addImages:
        await _pickImagesForCurrentEditor();
      case _CreateMediaOption.capture:
        await _openCameraForCurrentEditor(
          forcedMode: isVideoState
              ? MediaPickerEntryMode.video
              : MediaPickerEntryMode.image,
        );
      case _CreateMediaOption.video:
        await _pickVideoForMedia();
    }
  }

  Future<void> _editCurrentVideo() async {
    final state = ref.read(createEditorProvider);
    if (!state.hasVideo) {
      return;
    }
    final result = await Navigator.of(context).push<VideoEditorResult>(
      MaterialPageRoute<VideoEditorResult>(
        fullscreenDialog: true,
        builder: (_) => VideoEditorPage(
          sourceVideoPath: state.originalVideoPath.trim().isEmpty
              ? state.videoPath
              : state.originalVideoPath,
          initialVideoPath: state.videoPath,
          initialThumbnailPath: state.videoThumbnail,
          initialDurationMs: state.videoDurationMs,
          initialTrimStartMs: state.videoTrimStartMs,
          initialTrimEndMs: state.videoTrimEndMs,
          initialCoverTimeMs: state.videoCoverTimeMs,
          initialMuted: state.videoMuted,
        ),
      ),
    );
    if (!mounted || result == null) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .applyVideoEditing(
          videoPath: result.videoPath,
          thumbnailPath: result.thumbnailPath,
          videoDurationMs: result.durationMs,
          trimStartMs: result.trimStartMs,
          trimEndMs: result.trimEndMs,
          coverTimeMs: result.coverTimeMs,
          muted: result.muted,
          originalVideoPath: result.originalVideoPath,
        );
    await _reportEvent('create_media_video_edited', <String, dynamic>{
      'muted': result.muted,
      'trimStartMs': result.trimStartMs,
      'trimEndMs': result.trimEndMs,
    });
  }

  Future<String?> _generateVideoThumbnail(String path) async {
    try {
      return await VideoThumbnail.thumbnailFile(
        video: path,
        imageFormat: ImageFormat.JPEG,
        quality: 80,
      );
    } catch (_) {
      return null;
    }
  }

  Future<int> _loadVideoDurationMs(String path) async {
    final controller = VideoPlayerController.file(File(path));
    try {
      await controller.initialize();
      return math.max(controller.value.duration.inMilliseconds, 1000);
    } catch (_) {
      return 0;
    } finally {
      await controller.dispose();
    }
  }

  _VideoEditContext _deriveVideoEditContext({
    required CreateEditorStateV2 previousState,
    required int nextDurationMs,
  }) {
    if (!previousState.hasVideo || nextDurationMs <= 0) {
      return _VideoEditContext(
        trimStartMs: 0,
        trimEndMs: 0,
        coverTimeMs: 0,
        muted: false,
      );
    }
    final previousDuration = previousState.videoDurationMs > 0
        ? previousState.videoDurationMs
        : math.max(previousState.videoTrimEndMs, 1000);
    final previousStart = previousState.videoTrimStartMs.clamp(
      0,
      previousDuration,
    );
    final previousEnd = previousState.videoTrimEndMs > 0
        ? previousState.videoTrimEndMs.clamp(
            previousStart + 100,
            previousDuration,
          )
        : previousDuration;
    final startRatio = previousStart / previousDuration;
    final endRatio = previousEnd / previousDuration;
    final coverRatio = previousState.videoCoverTimeMs > 0
        ? previousState.videoCoverTimeMs.clamp(previousStart, previousEnd) /
              previousDuration
        : (startRatio + endRatio) / 2;
    final nextStart =
        (nextDurationMs * startRatio).round().clamp(
              0,
              math.max(nextDurationMs - 100, 0),
            )
            as int;
    final rawNextEnd = (nextDurationMs * endRatio).round();
    final nextEnd = rawNextEnd.clamp(nextStart + 100, nextDurationMs);
    final nextCover = (nextDurationMs * coverRatio).round().clamp(
      nextStart,
      nextEnd,
    );
    final keepsFullRange = nextStart == 0 && nextEnd == nextDurationMs;
    return _VideoEditContext(
      trimStartMs: nextStart,
      trimEndMs: keepsFullRange ? 0 : nextEnd,
      coverTimeMs: nextCover,
      muted: previousState.videoMuted,
    );
  }

  Future<void> _editCurrentImage(int index) async {
    final state = ref.read(createEditorProvider);
    if (index < 0 || index >= state.imagePaths.length) {
      return;
    }
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        fullscreenDialog: true,
        builder: (_) => ImageEditorPage(
          initialPath: state.imagePaths[index],
          source: 'create',
          index: index,
          total: state.imagePaths.length,
          imagePaths: state.imagePaths,
        ),
      ),
    );
    if (!mounted || result is! String || result.trim().isEmpty) {
      return;
    }
    final next = List<String>.from(state.imagePaths);
    next[index] = result;
    ref
        .read(createEditorProvider.notifier)
        .setImages(next, editorKind: state.editorKind, currentIndex: index);
  }

  Future<void> _editArticlePageImage(ArticlePageData page) async {
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: 1,
    );
    if (!mounted || result == null || result.items.isEmpty) {
      return;
    }
    final path = result.items.first.path.trim();
    if (path.isEmpty) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .replaceArticlePageImageFromBinding(page.binding!, path);
  }

  Future<List<CreateCircleOption>> _loadJoinedCircles() {
    return _circleService.listCircles(ref.read(circleRepositoryProvider));
  }

  Future<PublishSettings?> _showPublishConfirmationSheet(
    CreateEditorStateV2 state,
  ) async {
    final joinedCircles = await _loadJoinedCircles();
    if (!mounted) {
      return null;
    }
    return Navigator.of(context).push<PublishSettings>(
      CupertinoPageRoute<PublishSettings>(
        fullscreenDialog: true,
        builder: (_) => _CreatePublishConfirmSheet(
          initialSettings: state.settings,
          title: state.title.trim(),
          body: state.body.trim(),
          imageCount: state.imagePaths.length,
          hasVideo: state.hasVideo,
          locationService: _locationService,
          joinedCircles: joinedCircles,
          recommendedCircles: mockRecommendedCircles,
        ),
      ),
    );
  }

  int _paragraphCount(String text) {
    return text
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
  }

  List<TextInputFormatter> get _bodyInputFormatters => <TextInputFormatter>[
    LengthLimitingTextInputFormatter(_kMaxBodyLength),
  ];

  bool _shouldPublishAsArticle(CreateEditorStateV2 state) {
    return state.title.trim().isNotEmpty ||
        state.imagePaths.isNotEmpty ||
        state.body.trim().length >= 140 ||
        _paragraphCount(state.body) >= 2;
  }

  bool _canPublish(CreateEditorStateV2 state) {
    if (state.editorKind == CreateEditorKind.media) {
      return state.hasImages ||
          state.hasVideo ||
          state.hasBody ||
          state.hasTitle;
    }
    return state.hasBody || state.hasTitle || state.hasImages;
  }

  String _articleSummaryForState(CreateEditorStateV2 state) {
    final plainText = state.body.trim();
    if (plainText.isEmpty) {
      return state.imagePaths.isNotEmpty ? '图文内容' : '';
    }
    if (plainText.length <= 120) {
      return plainText;
    }
    return '${plainText.substring(0, 120)}...';
  }

  List<Map<String, dynamic>> _buildArticleCards(CreateEditorStateV2 state) {
    return buildArticleCardsFromPages(state.articlePages);
  }

  Map<String, dynamic> _buildCreatePayload(CreateEditorStateV2 state) {
    final settings = state.settings.toPayloadFields();
    final coverAssetPath = _coverAssetPathForState(state);
    if (state.editorKind == CreateEditorKind.media) {
      if (state.hasVideo) {
        return <String, dynamic>{
          'type': 'video',
          'contentType': 'video',
          'title': state.title.trim(),
          'body': state.body.trim(),
          'videoUrl': state.videoPath,
          'mediaUrls': <String>[state.videoPath],
          'coverUrl': coverAssetPath,
          ...settings,
        };
      }
      return <String, dynamic>{
        'type': 'image',
        'contentType': 'image',
        'title': state.title.trim(),
        'body': state.body.trim(),
        'mediaUrls': state.imagePaths,
        'coverUrl': coverAssetPath,
        ...settings,
      };
    }
    final asArticle = _shouldPublishAsArticle(state);
    if (asArticle) {
      final articleBody = buildArticlePlainTextFromDocument(
        state.articleDocument,
      ).trim();
      return <String, dynamic>{
        'type': 'article',
        'contentType': 'article',
        'title': state.title.trim(),
        'body': articleBody.isNotEmpty
            ? articleBody
            : _articleSummaryForState(state),
        'mediaUrls': state.imagePaths,
        'coverUrl': coverAssetPath,
        'articleTemplate': state.articleTemplate.name,
        'articleFontPreset': state.articleFontPreset.name,
        'articleDocument': state.articleDocument.toMap(),
        'articlePages': state.articlePages
            .map((page) => page.toMap())
            .toList(growable: false),
        'cards': _buildArticleCards(state),
        'articleBlocks': state.articleBlocks
            .map((block) => block.toMap())
            .toList(growable: false),
        ...settings,
      };
    }
    return <String, dynamic>{
      'type': 'moment',
      'contentType': 'micro',
      'title': state.title.trim(),
      'body': state.body.trim(),
      'mediaUrls': state.imagePaths,
      'coverUrl': coverAssetPath,
      ...settings,
    };
  }

  String _extractPostId(Map<String, dynamic> payload) {
    return (payload['_id'] ?? payload['postId'] ?? payload['id'] ?? '')
        .toString()
        .trim();
  }

  Future<Map<String, dynamic>> _attachActivePersonaContext(
    Map<String, dynamic> payload,
  ) async {
    final activeContext = await ref.read(activePersonaContextProvider.future);
    final mode = ref.read(appDataSourceModeProvider);
    if (mode == AppDataSourceMode.remote && activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return <String, dynamic>{
      ...payload,
      if (activeContext.subAccountId.isNotEmpty)
        'personaId': activeContext.subAccountId,
      if (activeContext.profileSubjectId.isNotEmpty)
        'profileSubjectId': activeContext.profileSubjectId,
      if (activeContext.personaContextVersion.isNotEmpty)
        'personaContextVersion': activeContext.personaContextVersion,
    };
  }

  Future<void> _publish() async {
    var state = ref.read(createEditorProvider);
    if (_isPublishing) {
      return;
    }
    if (!_canPublish(state)) {
      AppToast.show(context, '先写点内容');
      return;
    }
    if (_useImmersiveArticleExperience(state)) {
      final proceed = await Navigator.of(context).push<bool>(
        CupertinoPageRoute<bool>(
          fullscreenDialog: true,
          builder: (_) => const ArticlePreviewPage(),
        ),
      );
      if (proceed != true) {
        return;
      }
      state = ref.read(createEditorProvider);
    }
    final confirmedSettings = await _showPublishConfirmationSheet(state);
    if (confirmedSettings == null) {
      return;
    }
    final publishState = state.copyWith(settings: confirmedSettings);
    ref.read(createEditorProvider.notifier).setSettings(confirmedSettings);
    setState(() => _isPublishing = true);
    try {
      final repository = ref.read(contentRepositoryProvider);
      final payload = await _attachActivePersonaContext(
        _buildCreatePayload(publishState),
      );
      final created = await repository.createPost(payload: payload);
      final postId = _extractPostId(created);
      if (postId.isEmpty) {
        throw StateError('missing post id');
      }
      await repository.publishPost(
        postId: postId,
        payload: confirmedSettings.toPayloadFields(),
      );
      await _clearCurrentDraft();
      await _reportEvent('create_publish_success', <String, dynamic>{
        'contentType': payload['contentType'],
      });
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.publishAction);
      _doClose();
    } catch (error) {
      await _reportEvent('create_publish_failure');
      if (mounted) {
        AppToast.show(
          context,
          '$error'.contains('active persona context')
              ? '当前分身上下文未就绪，请稍后重试'
              : context.l10n.loadFailed,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isPublishing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(createEditorProvider);
    _syncControllersFromState(state);
    if (_useImmersiveArticleExperience(state)) {
      return _buildImmersiveArticlePage(state);
    }
    final background = CupertinoColors.systemGroupedBackground.resolveFrom(
      context,
    );
    final foreground = CupertinoColors.label.resolveFrom(context);
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        child: Material(
          key: TestKeys.createPage,
          color: background,
          child: SafeArea(
            bottom: false,
            child: Column(
              children: <Widget>[
                _buildHeader(
                  foreground: foreground,
                  secondary: secondary,
                  state: state,
                  collapseProgress: _heroCollapseProgress,
                ),
                Expanded(
                  child: SingleChildScrollView(
                    controller: _scrollController,
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.containerSm,
                      AppSpacing.containerMd,
                      MediaQuery.of(context).padding.bottom +
                          AppSpacing.containerLg,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        if (!_editorV2Enabled) _buildRollbackBanner(secondary),
                        if (state.editorKind == CreateEditorKind.media)
                          _buildMediaEditor(state)
                        else
                          _buildTextEditor(state),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImmersiveArticlePage(CreateEditorStateV2 state) {
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final foreground = CupertinoColors.label.resolveFrom(context);
    final divider = CupertinoColors.separator.resolveFrom(context);
    final actionTint = _isPublishing
        ? CupertinoColors.tertiaryLabel.resolveFrom(context)
        : AppColors.iosAccentLight;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        child: Material(
          key: TestKeys.createPage,
          color: background,
          child: SafeArea(
            bottom: false,
            child: Column(
              children: <Widget>[
                Container(
                  height: AppSpacing.toolbarHeight,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  decoration: BoxDecoration(
                    color: background.withValues(alpha: 0.98),
                    border: Border(
                      bottom: BorderSide(
                        color: divider.withValues(alpha: 0.45),
                        width: AppSpacing.hairline,
                      ),
                    ),
                  ),
                  child: Stack(
                    alignment: Alignment.center,
                    children: <Widget>[
                      Align(
                        alignment: Alignment.centerLeft,
                        child: CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: const Size.square(
                            AppSpacing.iconButtonMinSizeSm,
                          ),
                          onPressed: _onCloseRequest,
                          child: Icon(CupertinoIcons.clear, color: foreground),
                        ),
                      ),
                      Text(
                        '文章编辑',
                        style: TextStyle(
                          color: foreground,
                          fontSize: AppTypography.base,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                      Align(
                        alignment: Alignment.centerRight,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            CupertinoButton(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.intraGroupSm,
                              ),
                              minimumSize: const Size.square(
                                AppSpacing.iconButtonMinSizeSm,
                              ),
                              onPressed: _savedDrafts.isEmpty
                                  ? null
                                  : () => _showDraftsSheet(),
                              child: Text(
                                '草稿',
                                style: TextStyle(
                                  color: _savedDrafts.isEmpty
                                      ? CupertinoColors.tertiaryLabel
                                            .resolveFrom(context)
                                      : foreground,
                                  fontSize: AppTypography.sm,
                                  fontWeight: AppTypography.medium,
                                ),
                              ),
                            ),
                            CupertinoButton(
                              key: TestKeys.createPublishButton,
                              padding: EdgeInsets.zero,
                              minimumSize: const Size.square(
                                AppSpacing.iconButtonMinSizeSm,
                              ),
                              onPressed: _isPublishing ? null : _publish,
                              child: Text(
                                _isPublishing ? '处理中' : '下一步',
                                style: TextStyle(
                                  color: actionTint,
                                  fontSize: AppTypography.base,
                                  fontWeight: AppTypography.semiBold,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: AnimatedPadding(
                    duration: const Duration(milliseconds: 220),
                    curve: Curves.easeOutCubic,
                    padding: EdgeInsets.only(top: AppSpacing.containerSm),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        if (!_editorV2Enabled) ...<Widget>[
                          Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerMd,
                            ),
                            child: _buildRollbackBanner(
                              CupertinoColors.secondaryLabel.resolveFrom(
                                context,
                              ),
                            ),
                          ),
                          SizedBox(height: AppSpacing.interGroupSm),
                        ],
                        Expanded(child: _buildTextEditor(state)),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRollbackBanner(Color secondary) {
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Text(
        '当前处于编辑器回退模式，保留双编辑器骨架并关闭增强提示。',
        style: TextStyle(color: secondary, fontSize: AppTypography.sm),
      ),
    );
  }

  Widget _buildHeader({
    required Color foreground,
    required Color secondary,
    required CreateEditorStateV2 state,
    required double collapseProgress,
  }) {
    final title = _pageTitleForState(state);
    final divider = CupertinoColors.separator.resolveFrom(context);
    final chrome = CupertinoColors.systemBackground
        .resolveFrom(context)
        .withValues(alpha: lerpDouble(0.78, 0.94, collapseProgress)!);
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
          decoration: BoxDecoration(
            color: chrome,
            border: Border(
              bottom: BorderSide(
                color: divider.withValues(alpha: 0.45),
                width: AppSpacing.hairline,
              ),
            ),
          ),
          child: SizedBox(
            height: AppSpacing.toolbarHeight,
            child: Stack(
              children: <Widget>[
                Align(
                  alignment: Alignment.centerLeft,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      _buildHeaderIconButton(
                        key: TestKeys.createCloseButton,
                        icon: CupertinoIcons.xmark,
                        color: foreground,
                        onPressed: _onCloseRequest,
                      ),
                      if (_savedDrafts.isNotEmpty)
                        Padding(
                          padding: EdgeInsets.only(
                            left: AppSpacing.intraGroupXs,
                          ),
                          child: CupertinoButton(
                            key: TestKeys.createDraftsButton,
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerSm,
                              vertical: AppSpacing.intraGroupXs,
                            ),
                            minimumSize: const Size.square(
                              AppSpacing.buttonHeightSm,
                            ),
                            color: CupertinoColors.systemFill.resolveFrom(
                              context,
                            ),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusTwenty,
                            ),
                            onPressed: _showDraftsSheet,
                            child: Text(
                              UITextConstants.drafts,
                              style: TextStyle(
                                color: secondary,
                                fontSize: AppTypography.smPlus,
                                fontWeight: AppTypography.medium,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                Center(
                  child: Opacity(
                    opacity: lerpDouble(0.34, 1, collapseProgress)!,
                    child: Transform.translate(
                      offset: Offset(0, lerpDouble(6, 0, collapseProgress)!),
                      child: Text(
                        title,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: foreground,
                          fontSize: AppTypography.xl,
                          fontWeight: AppTypography.semiBold,
                          letterSpacing: 0.2,
                        ),
                      ),
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: CupertinoButton(
                    key: TestKeys.createPublishButton,
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                    ),
                    minimumSize: const Size.square(AppSpacing.buttonHeightSm),
                    color: AppColors.iosAccentLight,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusTwenty,
                    ),
                    onPressed: _isPublishing ? null : _publish,
                    child: _isPublishing
                        ? const CupertinoActivityIndicator(color: Colors.white)
                        : const Text(
                            '下一步',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: AppTypography.base,
                              fontWeight: AppTypography.semiBold,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeaderIconButton({
    required Key key,
    required IconData icon,
    required Color color,
    required VoidCallback onPressed,
  }) {
    return CupertinoButton(
      key: key,
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        width: AppSpacing.buttonHeightSm,
        height: AppSpacing.buttonHeightSm,
        decoration: BoxDecoration(
          color: CupertinoColors.systemFill.resolveFrom(context),
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: color, size: AppSpacing.iconMedium),
      ),
    );
  }

  Widget _buildTextEditor(CreateEditorStateV2 state) {
    return ArticleEditor(
      state: state,
      titleController: _titleController,
      titleFocusNode: _titleFocusNode,
      onTitleChanged: (value) {
        ref.read(createEditorProvider.notifier).updateTitle(value);
      },
      onUpdatePageText: (page, value) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticlePageTextFromBinding(page.binding!, value);
      },
      onEditPageImage: _editArticlePageImage,
      onUpdatePageImageLayout: (page, layout) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticlePageImageLayoutFromBinding(page.binding!, layout);
      },
      onRemovePage: (page) {
        if (page.contentBlocks.isNotEmpty) {
          ref
              .read(createEditorProvider.notifier)
              .removeArticleBlocks(page.contentBlocks.map((block) => block.id));
        }
        ref
            .read(createEditorProvider.notifier)
            .removeArticlePageFromBinding(page.binding!);
      },
      onActivePageChanged: (pageId) {
        ref.read(createEditorProvider.notifier).setActiveArticlePage(pageId);
      },
      onActiveBlockChanged: (blockId) {
        ref.read(createEditorProvider.notifier).setActiveArticleBlock(blockId);
      },
      onUpdateTextBlock: (blockId, value) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleTextBlock(blockId, value);
      },
      onInsertTextBlock: (afterBlockId, type) {
        return ref
            .read(createEditorProvider.notifier)
            .insertArticleTextBlock(afterBlockId: afterBlockId, type: type);
      },
      onUpdateTextBlockType: (blockId, type) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleTextBlockType(blockId, type);
      },
      onRemoveTextBlock: (blockId) {
        ref.read(createEditorProvider.notifier).removeArticleBlock(blockId);
      },
      onCoverChanged: (imagePath) {
        ref.read(createEditorProvider.notifier).setArticleCoverImage(imagePath);
      },
      onTemplateChanged: (template) {
        ref.read(createEditorProvider.notifier).setArticleTemplate(template);
      },
      onFontPresetChanged: (fontPreset) {
        ref
            .read(createEditorProvider.notifier)
            .setArticleFontPreset(fontPreset);
      },
      immersive: widget.initialAction == EditorStartAction.write,
    );
  }

  Widget _buildMediaEditor(CreateEditorStateV2 state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildMediaComposerSection(
          state: state,
          title: _mediaHeaderHintForState(state),
          trailing: state.hasVideo
              ? '仅 1 个视频'
              : '${state.imagePaths.length} / $_kMaxMediaImages',
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _buildTitleSection(
          state: state,
          titleFieldKey: state.mediaKind == CreateMediaKind.video
              ? TestKeys.createVideoTitleInput
              : TestKeys.createPhotoTitleInput,
        ),
        SizedBox(height: AppSpacing.interGroupSm),
        _buildInputPanel(
          label: '正文',
          currentLength: state.body.length,
          input: CupertinoTextField(
            key: state.mediaKind == CreateMediaKind.video
                ? TestKeys.createVideoBodyInput
                : TestKeys.createPhotoBodyInput,
            controller: _bodyController,
            focusNode: _bodyFocusNode,
            inputFormatters: _bodyInputFormatters,
            maxLines: null,
            minLines: 4,
            padding: EdgeInsets.zero,
            placeholder: '补一段配文，让内容更完整',
            decoration: const BoxDecoration(),
            onChanged: (value) {
              ref.read(createEditorProvider.notifier).updateBody(value);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildMediaComposerSection({
    required CreateEditorStateV2 state,
    required String title,
    required String trailing,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildSectionHeader(title: title, trailing: trailing),
        SizedBox(height: AppSpacing.intraGroupSm),
        _buildSurfacePanel(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _buildMediaStrip(
                state: state,
                onAdd: state.hasVideo
                    ? _pickVideoForMedia
                    : () => _showAddMediaOptions(state),
                onTapImage: _editCurrentImage,
                onRemove: (index) {
                  if (state.mediaKind == CreateMediaKind.video) {
                    ref.read(createEditorProvider.notifier).clearVideo();
                  } else {
                    ref
                        .read(createEditorProvider.notifier)
                        .removeImageAt(index);
                  }
                },
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader({required String title, String? trailing}) {
    return Row(
      children: <Widget>[
        if (title.trim().isNotEmpty)
          Text(
            title,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
              letterSpacing: 0.2,
            ),
          ),
        const Spacer(),
        if (trailing != null)
          Text(
            trailing,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
      ],
    );
  }

  Widget _buildSurfacePanel({required Widget child, EdgeInsets? padding}) {
    final panelBackground = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final separator = CupertinoColors.separator.resolveFrom(context);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelBackground,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: separator.withValues(alpha: 0.18),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }

  Widget _buildInputPanel({
    required String label,
    required int currentLength,
    required Widget input,
  }) {
    return _buildSurfacePanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                label,
                style: const TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              const Spacer(),
              Text(
                '$currentLength / $_kMaxBodyLength',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.containerSm,
            ),
            decoration: BoxDecoration(
              color: CupertinoColors.systemBackground.resolveFrom(context),
              borderRadius: BorderRadius.circular(AppSpacing.containerSm),
            ),
            child: DefaultTextStyle(
              style: TextStyle(
                fontSize: AppTypography.base,
                color: CupertinoColors.label.resolveFrom(context),
                height: AppTypography.bodyLineHeight,
              ),
              child: input,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMediaStrip({
    required CreateEditorStateV2 state,
    required Future<void> Function() onAdd,
    required Future<void> Function(int index) onTapImage,
    required void Function(int index) onRemove,
  }) {
    final isVideo =
        state.mediaKind == CreateMediaKind.video && state.videoPath.isNotEmpty;
    final items = isVideo
        ? <String>[
            state.videoThumbnail.trim().isEmpty
                ? state.videoPath
                : state.videoThumbnail,
          ]
        : state.imagePaths;
    return LayoutBuilder(
      builder: (context, constraints) {
        final spacing = AppSpacing.intraGroupSm;
        final columns = _mediaColumnsForWidth(constraints.maxWidth);
        final tileWidth =
            ((constraints.maxWidth - spacing * (columns - 1)) / columns)
                .clamp(72.0, 148.0)
                .toDouble();
        final tileHeight = tileWidth * _mediaTileAspectRatioForColumns(columns);
        final addEnabled = state.editorKind == CreateEditorKind.text
            ? true
            : _canAddMoreImages(state);
        final addLabel = state.editorKind == CreateEditorKind.text
            ? '添加图片'
            : (items.isEmpty ? '添加' : '添加图片');
        if (isVideo) {
          final videoWidth = math
              .min(tileWidth * 1.2, constraints.maxWidth)
              .toDouble();
          return Column(
            children: <Widget>[
              Align(
                alignment: Alignment.center,
                child: _buildMediaTile(
                  assetPath: items.first,
                  index: 0,
                  isVideo: true,
                  width: videoWidth,
                  height: tileHeight,
                  showDragHandle: false,
                  isEmphasized: true,
                  onTap: _editCurrentVideo,
                  onRemove: () => onRemove(0),
                ),
              ),
              SizedBox(height: spacing),
              Text(
                '轻点视频编辑，支持裁切、静音和精细选帧',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onAdd,
                child: const Text('更换视频'),
              ),
            ],
          );
        }
        if (items.isEmpty) {
          return Align(
            alignment: Alignment.centerLeft,
            child: _AddThumbnailButton(
              key: TestKeys.createMediaAddButton,
              onPressed: onAdd,
              width: tileWidth,
              height: tileHeight,
              label: addLabel,
              enabled: addEnabled,
            ),
          );
        }

        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: <Widget>[
            for (int index = 0; index < items.length; index++)
              SizedBox(
                width: tileWidth,
                child: DragTarget<String>(
                  onWillAcceptWithDetails: (details) =>
                      details.data != items[index],
                  onMove: (details) {
                    _autoScrollDuringMediaDrag(details.offset);
                    _reorderImageByPath(details.data, index);
                  },
                  builder: (context, candidateData, rejectedData) {
                    final assetPath = items[index];
                    final tile = _buildMediaTile(
                      assetPath: assetPath,
                      index: index,
                      isVideo: false,
                      width: tileWidth,
                      height: tileHeight,
                      showDragHandle: true,
                      isEmphasized: candidateData.isNotEmpty,
                      isPressed: _pressedMediaPath == assetPath,
                      onTap: () => onTapImage(index),
                      onRemove: () => onRemove(index),
                    );
                    return LongPressDraggable<String>(
                      data: assetPath,
                      onDragStarted: () {
                        HapticFeedback.mediumImpact();
                        setState(() {
                          _draggingMediaPath = assetPath;
                          _pressedMediaPath = assetPath;
                        });
                      },
                      onDragUpdate: (details) {
                        _autoScrollDuringMediaDrag(details.globalPosition);
                      },
                      onDragEnd: (_) {
                        HapticFeedback.selectionClick();
                        if (!mounted) {
                          return;
                        }
                        setState(() {
                          _draggingMediaPath = null;
                          _pressedMediaPath = null;
                        });
                      },
                      onDraggableCanceled: (_, offset) {
                        _autoScrollDuringMediaDrag(offset);
                        if (!mounted) {
                          return;
                        }
                        setState(() {
                          _draggingMediaPath = null;
                          _pressedMediaPath = null;
                        });
                      },
                      onDragCompleted: () {
                        if (!mounted) {
                          return;
                        }
                        setState(() {
                          _draggingMediaPath = null;
                          _pressedMediaPath = null;
                        });
                      },
                      feedback: Material(
                        color: Colors.transparent,
                        child: Transform.scale(
                          scale: 1.03,
                          child: _buildMediaTile(
                            assetPath: assetPath,
                            index: index,
                            isVideo: false,
                            width: tileWidth,
                            height: tileHeight,
                            showDragHandle: true,
                            showRemoveButton: false,
                            isEmphasized: true,
                            showFloatingShadow: true,
                            onTap: () async {},
                            onRemove: () {},
                          ),
                        ),
                      ),
                      childWhenDragging: Opacity(opacity: 0.18, child: tile),
                      child: AnimatedOpacity(
                        duration: const Duration(milliseconds: 180),
                        opacity: _draggingMediaPath == assetPath ? 0.84 : 1,
                        child: tile,
                      ),
                    );
                  },
                ),
              ),
            SizedBox(
              width: tileWidth,
              child: DragTarget<String>(
                onWillAcceptWithDetails: (details) =>
                    items.isNotEmpty && details.data != items.last,
                onMove: (details) {
                  _autoScrollDuringMediaDrag(details.offset);
                  final latestItems = ref.read(createEditorProvider).imagePaths;
                  final fromIndex = latestItems.indexOf(details.data);
                  if (fromIndex >= 0 && fromIndex != latestItems.length - 1) {
                    ref
                        .read(createEditorProvider.notifier)
                        .reorderImages(fromIndex, latestItems.length);
                  }
                },
                builder: (context, candidateData, rejectedData) {
                  return _AddThumbnailButton(
                    key: TestKeys.createMediaAddButton,
                    onPressed: onAdd,
                    width: tileWidth,
                    height: tileHeight,
                    label: addLabel,
                    isHighlighted: candidateData.isNotEmpty && addEnabled,
                    enabled: addEnabled,
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildMediaTile({
    required String assetPath,
    required int index,
    required bool isVideo,
    required double width,
    required double height,
    required Future<void> Function() onTap,
    required VoidCallback onRemove,
    bool isEmphasized = false,
    bool isPressed = false,
    bool showDragHandle = true,
    bool showRemoveButton = true,
    bool showFloatingShadow = false,
  }) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) {
        if (!mounted) {
          return;
        }
        setState(() {
          _pressedMediaPath = assetPath;
        });
      },
      onTapCancel: () {
        if (!mounted) {
          return;
        }
        setState(() {
          if (_pressedMediaPath == assetPath) {
            _pressedMediaPath = null;
          }
        });
      },
      onTap: () async {
        if (mounted) {
          setState(() {
            if (_pressedMediaPath == assetPath) {
              _pressedMediaPath = null;
            }
          });
        }
        await onTap();
      },
      child: SizedBox(
        width: width,
        height: height,
        child: Transform.scale(
          scale: isEmphasized ? 1.015 : 1.0,
          child: Stack(
            children: <Widget>[
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                curve: Curves.easeOutCubic,
                width: width,
                height: height,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.containerSm),
                  border: Border.all(
                    color: isEmphasized
                        ? AppColors.iosAccentLight
                        : CupertinoColors.separator
                              .resolveFrom(context)
                              .withValues(alpha: 0.12),
                    width: isEmphasized
                        ? AppSpacing.oneHalf
                        : AppSpacing.hairline,
                  ),
                  boxShadow: isEmphasized
                      ? <BoxShadow>[
                          BoxShadow(
                            color: AppColors.iosAccentLight.withValues(
                              alpha: showFloatingShadow ? 0.22 : 0.14,
                            ),
                            blurRadius: showFloatingShadow
                                ? 18
                                : AppSpacing.ten,
                            offset: Offset(0, showFloatingShadow ? 10 : 4),
                            spreadRadius: showFloatingShadow ? 1.5 : 0,
                          ),
                        ]
                      : const <BoxShadow>[],
                ),
                clipBehavior: Clip.antiAlias,
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    if (isVideo)
                      Stack(
                        fit: StackFit.expand,
                        children: <Widget>[
                          Image.file(
                            File(assetPath),
                            fit: BoxFit.cover,
                            errorBuilder: (context, error, stackTrace) =>
                                Container(
                                  decoration: const BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: <Color>[
                                        AppColors
                                            .createMediaFallbackGradientTop,
                                        AppColors
                                            .createMediaFallbackGradientBottom,
                                      ],
                                    ),
                                  ),
                                ),
                          ),
                          DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: <Color>[
                                  Colors.black.withValues(alpha: 0.08),
                                  Colors.black.withValues(alpha: 0.34),
                                ],
                              ),
                            ),
                          ),
                          Center(
                            child: Container(
                              width: AppSpacing.buttonHeight,
                              height: AppSpacing.buttonHeight,
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.28),
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: Colors.white.withValues(alpha: 0.14),
                                  width: AppSpacing.hairline,
                                ),
                              ),
                              child: Icon(
                                CupertinoIcons.play_fill,
                                color: Colors.white.withValues(alpha: 0.96),
                                size: AppSpacing.iconLarge,
                              ),
                            ),
                          ),
                        ],
                      )
                    else
                      Image.file(
                        File(assetPath),
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) =>
                            Container(color: Colors.black12),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        bottom: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: '编辑视频',
                          backgroundColor: Colors.black.withValues(alpha: 0.48),
                        ),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        top: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: '视频',
                          backgroundColor: Colors.black.withValues(alpha: 0.48),
                        ),
                      ),
                    if (!isVideo)
                      Positioned.fill(
                        child: IgnorePointer(
                          child: Center(
                            child: AnimatedOpacity(
                              duration: const Duration(milliseconds: 180),
                              opacity: isPressed
                                  ? 0.92
                                  : (isEmphasized ? 0.54 : 0.14),
                              child: ClipOval(
                                child: BackdropFilter(
                                  filter: ImageFilter.blur(
                                    sigmaX: AppSpacing.containerSm,
                                    sigmaY: AppSpacing.containerSm,
                                  ),
                                  child: Container(
                                    width: AppSpacing.buttonHeight,
                                    height: AppSpacing.buttonHeight,
                                    decoration: BoxDecoration(
                                      color: Colors.black.withValues(
                                        alpha: isPressed ? 0.2 : 0.08,
                                      ),
                                      shape: BoxShape.circle,
                                      border: Border.all(
                                        color: Colors.white.withValues(
                                          alpha: isPressed ? 0.18 : 0.06,
                                        ),
                                        width: AppSpacing.hairline,
                                      ),
                                    ),
                                    child: Icon(
                                      Icons.edit_square,
                                      size: AppSpacing.iconSmall + 2,
                                      color: Colors.white.withValues(
                                        alpha: isPressed ? 0.96 : 0.88,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    if (showDragHandle && !isVideo)
                      Positioned(
                        right: AppSpacing.intraGroupXs,
                        bottom: AppSpacing.intraGroupXs,
                        child: Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.intraGroupXs,
                            vertical: AppSpacing.intraGroupXs / 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.18),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusTwenty,
                            ),
                          ),
                          child: const Icon(
                            CupertinoIcons.line_horizontal_3,
                            size: AppTypography.base,
                            color: Colors.white,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (showRemoveButton)
                Positioned(
                  right: AppSpacing.intraGroupXs,
                  top: AppSpacing.intraGroupXs,
                  child: GestureDetector(
                    key: index == 0 ? TestKeys.createMediaRemoveButton : null,
                    onTap: onRemove,
                    child: ClipOval(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(
                          sigmaX: AppSpacing.containerSm,
                          sigmaY: AppSpacing.containerSm,
                        ),
                        child: Container(
                          width:
                              AppSpacing.iconMedium + AppSpacing.intraGroupSm,
                          height:
                              AppSpacing.iconMedium + AppSpacing.intraGroupSm,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.1),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.06),
                              width: AppSpacing.hairline,
                            ),
                          ),
                          child: Icon(
                            CupertinoIcons.xmark,
                            size: AppTypography.xsPlus,
                            color: Colors.white.withValues(alpha: 0.92),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTitleSection({
    required CreateEditorStateV2 state,
    required Key titleFieldKey,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (state.titlePresentation == TitlePresentation.collapsed &&
            state.title.trim().isEmpty)
          CupertinoButton(
            key: TestKeys.createTitleToggle,
            padding: EdgeInsets.zero,
            alignment: Alignment.centerLeft,
            onPressed: () {
              ref.read(createEditorProvider.notifier).expandTitle();
              _focusTitleField();
            },
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupSm,
              ),
              decoration: BoxDecoration(
                color: CupertinoColors.secondarySystemGroupedBackground
                    .resolveFrom(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                border: Border.all(
                  color: CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.14),
                  width: AppSpacing.hairline,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    CupertinoIcons.text_badge_plus,
                    size: AppSpacing.iconMedium,
                    color: AppColors.iosAccentLight,
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  Text(
                    '添加标题（可选）',
                    style: TextStyle(
                      color: AppColors.iosAccentLight,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          _buildSurfacePanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _buildSectionHeader(title: '标题', trailing: '可选'),
                SizedBox(height: AppSpacing.intraGroupSm),
                CupertinoTextField(
                  key: titleFieldKey,
                  controller: _titleController,
                  focusNode: _titleFocusNode,
                  padding: EdgeInsets.zero,
                  placeholder: '补一个能概括内容的标题',
                  decoration: const BoxDecoration(),
                  onChanged: (value) {
                    ref.read(createEditorProvider.notifier).updateTitle(value);
                  },
                  onEditingComplete: () {
                    if (_titleController.text.trim().isEmpty) {
                      ref
                          .read(createEditorProvider.notifier)
                          .collapseTitleIfEmpty();
                    }
                  },
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _PreviewBadge extends StatelessWidget {
  const _PreviewBadge({required this.label, this.backgroundColor});

  final String label;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: backgroundColor ?? Colors.black.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }
}

class _VideoEditContext {
  const _VideoEditContext({
    required this.trimStartMs,
    required this.trimEndMs,
    required this.coverTimeMs,
    required this.muted,
  });

  final int trimStartMs;
  final int trimEndMs;
  final int coverTimeMs;
  final bool muted;
}

class _AddThumbnailButton extends StatelessWidget {
  const _AddThumbnailButton({
    super.key,
    required this.onPressed,
    required this.width,
    required this.height,
    required this.label,
    this.isHighlighted = false,
    this.enabled = true,
  });

  final Future<void> Function() onPressed;
  final double width;
  final double height;
  final String label;
  final bool isHighlighted;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final accent = enabled
        ? AppColors.iosAccentLight
        : CupertinoColors.tertiaryLabel.resolveFrom(context);
    return GestureDetector(
      onTap: enabled ? () => onPressed() : null,
      child: Transform.scale(
        scale: isHighlighted ? 1.015 : 1.0,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          width: width,
          height: height,
          padding: EdgeInsets.all(AppSpacing.containerSm),
          decoration: BoxDecoration(
            color: enabled
                ? CupertinoColors.systemBackground.resolveFrom(context)
                : CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
                    context,
                  ),
            borderRadius: BorderRadius.circular(AppSpacing.containerSm),
            border: Border.all(
              color: enabled
                  ? (isHighlighted
                        ? AppColors.iosAccentLight
                        : AppColors.iosAccentLight.withValues(alpha: 0.24))
                  : CupertinoColors.separator
                        .resolveFrom(context)
                        .withValues(alpha: 0.18),
              width: isHighlighted ? AppSpacing.oneHalf : AppSpacing.hairline,
            ),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: enabled
                    ? AppColors.iosAccentLight.withValues(
                        alpha: isHighlighted ? 0.12 : 0.06,
                      )
                    : Colors.black.withValues(alpha: 0.02),
                blurRadius: isHighlighted ? 12 : AppSpacing.ten,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Icon(
                CupertinoIcons.add,
                color: accent,
                size: AppSpacing.iconLarge,
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: accent,
                  fontSize: AppTypography.smPlus,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CreateDraftsSheet extends StatelessWidget {
  const _CreateDraftsSheet({
    required this.drafts,
    required this.onSelect,
    required this.onDelete,
  });

  final List<CreateDraft> drafts;
  final ValueChanged<CreateDraft> onSelect;
  final ValueChanged<CreateDraft> onDelete;

  @override
  Widget build(BuildContext context) {
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: CupertinoColors.systemGroupedBackground.resolveFrom(
        context,
      ),
      maxHeightRatio: 0.72,
      contentPadding: const EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        0,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              AppSpacing.containerSm,
            ),
            child: Column(
              children: <Widget>[
                Text(
                  UITextConstants.drafts,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  '最近保存的内容会保留在这里',
                  style: TextStyle(
                    color: secondary,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ),
          ),
          Flexible(
            child: ListView.separated(
              shrinkWrap: true,
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                0,
                AppSpacing.containerSm,
                AppSpacing.containerSm,
              ),
              itemCount: drafts.length,
              separatorBuilder: (context, index) =>
                  const SizedBox(height: AppSpacing.intraGroupSm),
              itemBuilder: (context, index) {
                final draft = drafts[index];
                final preview = draft.previewText.trim().isEmpty
                    ? '继续完善这条内容'
                    : draft.previewText.trim();
                return Container(
                  decoration: BoxDecoration(
                    color: CupertinoColors.secondarySystemGroupedBackground
                        .resolveFrom(context),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                  ),
                  child: CupertinoListTile(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                      vertical: AppSpacing.intraGroupXs,
                    ),
                    title: Text(draft.draftLabel),
                    subtitle: Text(
                      preview,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: () => onDelete(draft),
                      child: Container(
                        width: AppSpacing.largeButtonSize,
                        height: AppSpacing.largeButtonSize,
                        decoration: BoxDecoration(
                          color: CupertinoColors.systemBackground.resolveFrom(
                            context,
                          ),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          CupertinoIcons.delete,
                          color: CupertinoColors.destructiveRed,
                        ),
                      ),
                    ),
                    onTap: () => onSelect(draft),
                  ),
                );
              },
            ),
          ),
          CupertinoButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text(UITextConstants.cancel),
          ),
        ],
      ),
    );
  }
}

enum _CreateMediaOption { addImages, capture, video }

class _CreatePublishConfirmSheet extends StatefulWidget {
  const _CreatePublishConfirmSheet({
    required this.initialSettings,
    required this.title,
    required this.body,
    required this.imageCount,
    required this.hasVideo,
    required this.locationService,
    required this.joinedCircles,
    required this.recommendedCircles,
  });

  final PublishSettings initialSettings;
  final String title;
  final String body;
  final int imageCount;
  final bool hasVideo;
  final CreateLocationService locationService;
  final List<CreateCircleOption> joinedCircles;
  final List<CreateCircleOption> recommendedCircles;

  @override
  State<_CreatePublishConfirmSheet> createState() =>
      _CreatePublishConfirmSheetState();
}

class _CreatePublishConfirmSheetState
    extends State<_CreatePublishConfirmSheet> {
  late PublishSettings _settings;
  bool _bodyExpanded = false;
  bool _previewReady = false;
  bool _settingsReady = false;
  bool _buttonReady = false;

  bool get _hasContentSummary =>
      widget.title.trim().isNotEmpty || widget.body.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _settings = widget.initialSettings;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _previewReady = true;
      });
      Future<void>.delayed(const Duration(milliseconds: 90), () {
        if (!mounted) {
          return;
        }
        setState(() {
          _settingsReady = true;
        });
      });
      Future<void>.delayed(const Duration(milliseconds: 190), () {
        if (!mounted) {
          return;
        }
        setState(() {
          _buttonReady = true;
        });
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return IosSelectionPageScaffold(
      pageKey: TestKeys.createPublishConfirmSheet,
      title: UITextConstants.publishSettingsTitle,
      onBack: () => Navigator.of(context).pop(),
      backgroundColor: AppColors.iosPageBackground(context),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.interGroupLg,
        ),
        children: <Widget>[
          _buildSheetEntrance(
            visible: _settingsReady,
            beginOffsetY: 0.035,
            beginScale: 0.988,
            child: _buildSettingsCard(context),
          ),
          if (_hasContentSummary) ...<Widget>[
            SizedBox(height: AppSpacing.interGroupMd),
            _buildSheetEntrance(
              visible: _previewReady,
              beginOffsetY: 0.028,
              beginScale: 0.992,
              child: _buildPreviewCard(context),
            ),
          ],
        ],
      ),
      bottomBar: _buildSheetEntrance(
        visible: _buttonReady,
        beginOffsetY: 0.045,
        beginScale: 0.992,
        child: _buildPublishBottomBar(context),
      ),
    );
  }

  Widget _buildSettingsCard(BuildContext context) {
    return IosSelectionSection(
      child: Column(
        children: <Widget>[
          _buildSettingRow(
            context: context,
            title: UITextConstants.whoCanSeeLabel,
            value: _settings.isPublic
                ? UITextConstants.visibilityPublic
                : '仅自己可见',
            onTap: _pickVisibility,
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(AppSpacing.radiusTwentyEight),
            ),
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          _buildSettingRow(
            context: context,
            title: UITextConstants.locationLabel,
            value: _settings.locationName.trim().isEmpty
                ? UITextConstants.locationHidden
                : _settings.locationName.trim(),
            onTap: _pickLocation,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          _buildSettingRow(
            context: context,
            title: UITextConstants.attachHomepageTitle,
            value: !_settings.isPublic
                ? '仅公开内容可关联'
                : _settings.homepage == null
                ? UITextConstants.attachHomepageNone
                : _settings.homepage!.title,
            onTap: _settings.isPublic ? _pickHomepage : null,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          _buildSettingRow(
            context: context,
            title: '同步圈子',
            value: !_settings.isPublic
                ? '仅公开内容可选'
                : _settings.circleNames.isEmpty
                ? '未选圈子'
                : _settings.circleNames.join('、'),
            onTap: _settings.isPublic ? _pickCircles : null,
            borderRadius: BorderRadius.vertical(
              bottom: Radius.circular(AppSpacing.radiusTwentyEight),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPublishBottomBar(BuildContext context) {
    return IosSelectionBottomBar(
      confirmButtonKey: TestKeys.createPublishConfirmButton,
      confirmLabel: '确认发布',
      onConfirm: () => Navigator.of(context).pop(_settings),
    );
  }

  Widget _buildPreviewCard(BuildContext context) {
    final metaLabel = widget.hasVideo
        ? '视频内容'
        : widget.imageCount > 0
        ? '${widget.imageCount} 张图片'
        : '文字内容';
    return AnimatedContainer(
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
          context,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.16),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.035),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: AnimatedSize(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.iosAccentLight.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusNinetyNine,
                    ),
                  ),
                  child: Text(
                    metaLabel,
                    style: TextStyle(
                      color: AppColors.iosAccentLight,
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ),
                const Spacer(),
                Text(
                  '内容概览',
                  style: TextStyle(
                    color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            if (widget.title.isNotEmpty) ...<Widget>[
              Text(
                widget.title,
                style: const TextStyle(
                  fontSize: AppTypography.xl,
                  fontWeight: AppTypography.semiBold,
                  height: AppTypography.lineHeightTight,
                ),
              ),
              if (widget.body.isNotEmpty)
                SizedBox(height: AppSpacing.intraGroupXs),
            ],
            if (widget.body.isNotEmpty)
              _ExpandablePreviewText(
                text: widget.body,
                expanded: _bodyExpanded,
                onToggle: () {
                  setState(() {
                    _bodyExpanded = !_bodyExpanded;
                  });
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildSheetEntrance({
    required Widget child,
    required bool visible,
    double beginOffsetY = 0.04,
    double beginScale = 0.985,
  }) {
    return AnimatedSlide(
      offset: visible ? Offset.zero : Offset(0, beginOffsetY),
      duration: const Duration(milliseconds: 360),
      curve: Curves.easeOutCubic,
      child: AnimatedScale(
        scale: visible ? 1 : beginScale,
        duration: const Duration(milliseconds: 420),
        curve: Curves.easeOutCubic,
        child: AnimatedOpacity(
          opacity: visible ? 1 : 0,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOutCubic,
          child: child,
        ),
      ),
    );
  }

  Widget _buildSettingRow({
    required BuildContext context,
    required String title,
    required String value,
    VoidCallback? onTap,
    BorderRadius borderRadius = BorderRadius.zero,
  }) {
    return IosSelectionOptionTile(
      title: Text(
        title,
        style: TextStyle(
          color: AppColors.iosLabel(context),
          fontSize: AppTypography.iosBody,
          fontWeight: AppTypography.normal,
        ),
      ),
      additionalInfo: value,
      additionalInfoTextStyle: TextStyle(
        color: AppColors.iosAccent(context),
        fontSize: AppTypography.iosBody,
        fontWeight: AppTypography.normal,
      ),
      showChevron: true,
      onTap: onTap,
      backgroundColor: Colors.transparent,
      pressedColor: AppColors.iosSecondaryFill(context),
      borderRadius: borderRadius,
    );
  }

  Future<void> _pickVisibility() async {
    final nextValue = await showAppActionSheet<bool>(
      context,
      title: '谁可以看',
      message: '公开内容可以同步到圈子，私密内容仅自己可见。',
      sections: [
        AppActionSheetSection<bool>(
          items: [
            AppActionSheetItem<bool>(
              value: true,
              label: '公开',
              icon: CupertinoIcons.globe,
              isSelected: _settings.isPublic,
            ),
            AppActionSheetItem<bool>(
              value: false,
              label: '仅自己可见',
              icon: CupertinoIcons.lock,
              isSelected: !_settings.isPublic,
            ),
          ],
        ),
      ],
    );
    if (nextValue == null) {
      return;
    }
    setState(() {
      _settings = _settings.copyWith(
        isPublic: nextValue,
        circleIds: nextValue ? _settings.circleIds : const <String>[],
        circleNames: nextValue ? _settings.circleNames : const <String>[],
        clearHomepage: !nextValue,
      );
    });
  }

  Future<void> _pickLocation() async {
    final option = await Navigator.of(context).push<CreateLocationOption>(
      CupertinoPageRoute<CreateLocationOption>(
        builder: (_) => PublishLocationSelectorPage(
          locationService: widget.locationService,
        ),
      ),
    );
    if (option == null) {
      return;
    }
    setState(() {
      _settings = _settings.copyWith(
        locationName: option.name,
        location: option == CreateLocationOption.hidden
            ? const <String, dynamic>{}
            : option.toLocationMap(),
      );
    });
  }

  Future<void> _pickCircles() async {
    final selected = await Navigator.of(context).push<Map<String, String>>(
      CupertinoPageRoute<Map<String, String>>(
        builder: (_) => PublishCircleSelectPage(
          joinedCircles: widget.joinedCircles,
          recommendedCircles: widget.recommendedCircles,
          initialSelected: <String, String>{
            for (var i = 0; i < _settings.circleIds.length; i++)
              _settings.circleIds[i]: i < _settings.circleNames.length
                  ? _settings.circleNames[i]
                  : _settings.circleIds[i],
          },
        ),
      ),
    );
    if (selected == null) {
      return;
    }
    setState(() {
      _settings = _settings.copyWith(
        circleIds: selected.keys.toList(growable: false),
        circleNames: selected.values.toList(growable: false),
      );
    });
  }

  Future<void> _pickHomepage() async {
    if (!mounted) {
      return;
    }
    final result = await context.push<HomepagePickerSelectionResult>(
      AppRoutePaths.homepagePicker(query: _settings.homepage?.title),
      extra: HomepagePickerPageRouteExtra(initialSelection: _settings.homepage),
    );
    if (!mounted || result == null) {
      return;
    }
    setState(() {
      _settings = result.clearSelection
          ? _settings.copyWith(clearHomepage: true)
          : _settings.copyWith(homepage: result.selection);
    });
  }
}

class _ExpandablePreviewText extends StatelessWidget {
  const _ExpandablePreviewText({
    required this.text,
    required this.expanded,
    required this.onToggle,
  });

  final String text;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    const maxLines = 3;
    final style = TextStyle(
      fontSize: AppTypography.base,
      color: CupertinoColors.label.resolveFrom(context),
      height: AppTypography.lineHeightCompact,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final textPainter = TextPainter(
          text: TextSpan(text: text, style: style),
          maxLines: maxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = textPainter.didExceedMaxLines;

        if (!isOverflow) {
          return Text(text, style: style);
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              text,
              style: style,
              maxLines: expanded ? null : maxLines,
              overflow: expanded ? null : TextOverflow.ellipsis,
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            CupertinoButton(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: const Size(
                AppSpacing.buttonHeightXs,
                AppSpacing.buttonHeightXs,
              ),
              color: AppColors.iosAccentLight.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              onPressed: onToggle,
              child: Text(
                expanded ? '收起' : '展开全文',
                style: const TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColors.iosAccentLight,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
