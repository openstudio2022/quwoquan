import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:video_thumbnail/video_thumbnail.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_typography_page.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_circle_select_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/video_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';

/// 创作入口主面；草稿 [CreateEditorState]（清单 ContentPublishDraftComposite）+ [PublishSettings]（强类型 POI）。
/// 发布确认摘要的帖子只读投影经 [postReadPreviewBundleFromPublishConfirmSummary]（draftPreview 表面）。
class CreatePage extends ConsumerStatefulWidget {
  const CreatePage({
    super.key,
    this.initialAction,
    this.initialTabKey,
    this.initialHomepage,
    this.initialDraftId,
  });

  final EditorStartAction? initialAction;
  final String? initialTabKey;
  final HomepageCanonicalReference? initialHomepage;

  /// 从全局「从草稿继续」进入时由路由 query 注入，与本地清单 id 对齐。
  final String? initialDraftId;

  @override
  ConsumerState<CreatePage> createState() => _CreatePageState();
}

class _CreatePageState extends ConsumerState<CreatePage> {
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

  /// 图片拖动过程中最后一次指针全局坐标（用于松手时按重叠面积落点）。
  Offset? _imageDragLastGlobal;
  final GlobalKey _createMediaAddStripKey = GlobalKey();
  final Map<String, GlobalKey> _mediaTileBoundsKeys = <String, GlobalKey>{};
  List<CreateDraft> _savedDrafts = <CreateDraft>[];
  String? _currentDraftId;

  /// 非 null 时 [ArticleEditor] 在该页展开文内图工具栏（如新插入图片后）。
  final ValueNotifier<String?> _revealArticleImageToolbarForPageId =
      ValueNotifier<String?>(null);

  /// 按 asset id 展开工具条（多图同页时优先于 [_revealArticleImageToolbarForPageId]）。
  final ValueNotifier<String?> _revealArticleImageToolbarForAssetId =
      ValueNotifier<String?>(null);

  bool get _unifiedCreateEditorEnabled =>
      ref.read(contentFeatureFlagProvider('enable_unified_create_editor'));

  bool _useImmersiveArticleExperience(CreateEditorState state) {
    return widget.initialAction == EditorStartAction.write &&
        state.editorKind == CreateEditorKind.text;
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
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
      final loaded = await CreateDraftLocalStorage.loadDraftsWithCurrentId();
      if (!mounted) {
        return;
      }
      setState(() {
        _savedDrafts = loaded.drafts;
        _currentDraftId = loaded.currentId;
      });

      final wantedId = widget.initialDraftId?.trim();
      CreateDraft? initialDraft;
      if (wantedId != null && wantedId.isNotEmpty) {
        for (final d in loaded.drafts) {
          if (d.id == wantedId) {
            initialDraft = d;
            break;
          }
        }
      }

      final notifier = ref.read(createEditorProvider.notifier);
      if (initialDraft != null) {
        notifier.reset(editorKind: initialDraft.state.editorKind);
        await _restoreDraft(initialDraft);
        _didApplyInitialAction = true;
      } else {
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
      }

      if (!mounted) {
        return;
      }
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_editor_ready',
        createEditorSurfaceExtrasReady(
          editorKind: ref.read(createEditorProvider).editorKind,
          unifiedCreateEditorEnabled: _unifiedCreateEditorEnabled,
        ),
      );
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
    _revealArticleImageToolbarForPageId.dispose();
    _revealArticleImageToolbarForAssetId.dispose();
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

  void _syncControllersFromState(CreateEditorState state) {
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

  String _pageTitleForState(CreateEditorState state) {
    if (_useImmersiveArticleExperience(state)) {
      return UITextConstants.createArticleSurfaceLongEdit;
    }
    return '创作';
  }

  String _mediaHeaderHintForState(CreateEditorState state) {
    if (state.hasVideo) {
      return '轻点视频编辑，可设置封面';
    }
    if (state.imagePaths.isEmpty) {
      return '先添加图片或视频';
    }
    return '拖拽排序，轻点编辑';
  }

  bool _canAddMoreImages(CreateEditorState state) {
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

  GlobalKey _mediaTileBoundsKeyForPath(String path) {
    return _mediaTileBoundsKeys.putIfAbsent(path, GlobalKey.new);
  }

  Rect? _rectFromGlobalKey(GlobalKey? key) {
    final ctx = key?.currentContext;
    if (ctx == null) {
      return null;
    }
    final box = ctx.findRenderObject();
    if (box is! RenderBox || !box.hasSize) {
      return null;
    }
    return box.localToGlobal(Offset.zero) & box.size;
  }

  double _rectOverlapArea(Rect a, Rect b) {
    final i = a.intersect(b);
    if (i.width <= 0 || i.height <= 0) {
      return 0;
    }
    return i.width * i.height;
  }

  /// 松手时按拖动矩形与各缩略图（及「添加」格）重叠面积取最大者，执行一次排序。
  void _applyImageReorderOnDragEnd({
    required String draggedPath,
    required double tileWidth,
    required double tileHeight,
    required bool addEnabled,
  }) {
    final latest = ref.read(createEditorProvider).imagePaths;
    final fromIndex = latest.indexOf(draggedPath);
    if (fromIndex < 0) {
      return;
    }
    final pos = _imageDragLastGlobal;
    if (pos == null) {
      return;
    }
    final dragRect = Rect.fromCenter(
      center: pos,
      width: tileWidth,
      height: tileHeight,
    );
    double bestArea = 0;
    int? bestTargetIndex;
    for (var i = 0; i < latest.length; i++) {
      if (i == fromIndex) {
        continue;
      }
      final path = latest[i];
      final tileRect = _rectFromGlobalKey(_mediaTileBoundsKeys[path]);
      if (tileRect == null) {
        continue;
      }
      final area = _rectOverlapArea(dragRect, tileRect);
      if (area > bestArea) {
        bestArea = area;
        bestTargetIndex = i;
      }
    }
    if (addEnabled) {
      final addRect = _rectFromGlobalKey(_createMediaAddStripKey);
      if (addRect != null) {
        final area = _rectOverlapArea(dragRect, addRect);
        if (area > bestArea) {
          bestArea = area;
          bestTargetIndex = latest.length;
        }
      }
    }
    if (bestTargetIndex != null && bestArea > 0) {
      _reorderImageByPath(draggedPath, bestTargetIndex);
    }
  }

  Future<void> _persistDrafts(
    List<CreateDraft> drafts,
    String? currentId,
  ) async {
    await CreateDraftLocalStorage.persistDrafts(drafts, currentId);
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
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_draft_saved',
      createEditorSurfaceExtrasEditorKind(nextDraft.state.editorKind),
    );
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
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_draft_restored',
      createEditorSurfaceExtrasEditorKind(draft.state.editorKind),
    );
    if (draft.state.editorKind == CreateEditorKind.text) {
      _focusBodyField();
    }
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
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createMediaPicker,
        ),
        fullscreenDialog: true,
        builder: (_) => CreateMediaPickerPage(
          entryMode: mode,
          maxSelection: maxSelection,
          initialSelection: initialSelection,
        ),
      ),
    );
  }

  /// 为文章编辑器在指定 node 之后插入图片（node 级操作）。
  Future<void> _pickImagesForArticleNode(String? afterNodeId) async {
    final state = ref.read(createEditorProvider);
    final remainingSlots =
        (_kMaxMediaImages - state.imagePaths.length).clamp(0, _kMaxMediaImages);
    if (remainingSlots <= 0) {
      AppToast.show(context, '最多添加 $_kMaxMediaImages 张图片');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null) return;
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(remainingSlots)
        .toList(growable: false);
    if (paths.isEmpty) return;
    final notifier = ref.read(createEditorProvider.notifier);
    var anchorNodeId = afterNodeId;
    for (final path in paths) {
      anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
  }

  Future<void> _pickImagesForArticleTextSelection(
    String nodeId,
    int selectionOffset,
  ) async {
    final state = ref.read(createEditorProvider);
    final remainingSlots =
        (_kMaxMediaImages - state.imagePaths.length).clamp(0, _kMaxMediaImages);
    if (remainingSlots <= 0) {
      AppToast.show(context, '最多添加 $_kMaxMediaImages 张图片');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null) return;
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(remainingSlots)
        .toList(growable: false);
    if (paths.isEmpty) return;
    final notifier = ref.read(createEditorProvider.notifier);
    var anchorNodeId = notifier.prepareTextNodeForImageInsertion(
      nodeId,
      selectionOffset,
    );
    for (final path in paths) {
      anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
  }

  Future<void> _pickImagesForCurrentEditor() async {
    // 文本编辑器走 node 级插入
    final state = ref.read(createEditorProvider);
    if (state.editorKind == CreateEditorKind.text) {
      await _pickImagesForArticleNode(null);
      return;
    }
    if (state.hasVideo && state.editorKind == CreateEditorKind.media) {
      AppToast.show(context, '请先删除当前视频，再改为图片');
      return;
    }
    final remainingSlots = state.editorKind == CreateEditorKind.text
        ? (_kMaxMediaImages - state.imagePaths.length).clamp(
            0,
            _kMaxMediaImages,
          )
        : _kMaxMediaImages;
    if (state.editorKind == CreateEditorKind.text && remainingSlots <= 0) {
      AppToast.show(context, '最多添加 $_kMaxMediaImages 张图片');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: state.editorKind == CreateEditorKind.text
          ? const <String>[]
          : state.imagePaths,
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
      if (paths.isNotEmpty) {
        var anchorNodeId = state.activeArticleBlockId;
        for (final path in paths) {
          anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
        }
      }
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_media_images_selected',
        createEditorSurfaceExtrasMediaBatch(
          count: paths.length,
          editorKind: state.editorKind,
        ),
      );
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .setImages(paths, editorKind: state.editorKind);
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
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
    await reportCreateEditorSurfaceEvent(ref, 'create_media_video_selected');
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
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageCamera,
        ),
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
      ref
          .read(createEditorProvider.notifier)
          .insertImageAfterNode(state.activeArticleBlockId, result.path);
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

  Future<void> _showAddMediaOptions(CreateEditorState state) async {
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
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageVideoEditor,
        ),
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
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_video_edited',
      createEditorSurfaceExtrasVideoEdited(
        muted: result.muted,
        trimStartMs: result.trimStartMs,
        trimEndMs: result.trimEndMs,
      ),
    );
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
    required CreateEditorState previousState,
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
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageImagePreview,
        ),
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

  Future<List<CreateCircleOption>> _loadJoinedCircles() {
    return _circleService.listCircles(ref.read(circleRepositoryProvider));
  }

  Future<PublishSettings?> _showPublishConfirmationSheet(
    CreateEditorState state,
  ) async {
    final joinedCircles = await _loadJoinedCircles();
    if (!mounted) {
      return null;
    }
    return Navigator.of(context).push<PublishSettings>(
      CupertinoPageRoute<PublishSettings>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPagePublishConfirm,
        ),
        fullscreenDialog: true,
        builder: (_) => _CreatePublishConfirmSheet(
          initialSettings: state.settings,
          contentIdentity: CreateDraft(
            id: '',
            updatedAtMs: 0,
            state: state,
          ).identity,
          title: state.title.trim(),
          body: state.body.trim(),
          imageCount: state.imagePaths.length,
          hasVideo: state.hasVideo,
          locationService: _locationService,
          joinedCircles: joinedCircles,
          recommendedCircles: publishFlowRecommendedCircleOptions(
            ref.read(circleRepositoryProvider),
          ),
        ),
      ),
    );
  }

  List<TextInputFormatter> get _bodyInputFormatters => <TextInputFormatter>[
    LengthLimitingTextInputFormatter(_kMaxBodyLength),
  ];

  bool _canPublish(CreateEditorState state) {
    if (state.editorKind == CreateEditorKind.media) {
      return state.hasImages ||
          state.hasVideo ||
          state.hasBody ||
          state.hasTitle;
    }
    return state.hasBody || state.hasTitle || state.hasImages;
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
          settings: const RouteSettings(
            name: PageAccessInternalRoutes.createPageArticleTypography,
          ),
          fullscreenDialog: true,
          builder: (_) => const ArticleTypographyPage(),
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
      final payload = await attachActivePersonaToCreatePayload(
        ref,
        buildCreatePostPayloadMap(publishState),
      );
      final created = await repositoryCreatePost(repository, payload);
      final postId = created.id;
      if (postId.isEmpty) {
        throw StateError('missing post id');
      }
      await repositoryPublishPostWithSettings(
        repository,
        postId: postId,
        settings: confirmedSettings,
      );
      await _clearCurrentDraft();
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_publish_success',
        createEditorSurfaceExtrasPublishSuccess(payload),
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.publishAction);
      _doClose();
    } catch (error) {
      await reportCreateEditorSurfaceEvent(ref, 'create_publish_failure');
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
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        // Match [AppScaffold]: transparent Material gives Text a Material ancestor
        // so debug / fallback styling does not draw yellow underlines under labels.
        child: Material(
          type: MaterialType.transparency,
          child: KeyedSubtree(
            key: TestKeys.createPage,
            child: ColoredBox(
              color: background,
              child: SafeArea(
                top: false,
                bottom: false,
                child: Column(
                  children: <Widget>[
                    _buildHeader(
                      state: state,
                      collapseProgress: _heroCollapseProgress,
                    ),
                    Expanded(
                      child: state.editorKind == CreateEditorKind.media
                          ? SingleChildScrollView(
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
                                  if (!_unifiedCreateEditorEnabled)
                                    _buildRollbackBanner(
                                      CupertinoColors.secondaryLabel
                                          .resolveFrom(context),
                                    ),
                                  _buildMediaEditor(state),
                                ],
                              ),
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: <Widget>[
                                if (!_unifiedCreateEditorEnabled)
                                  Padding(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpacing.containerMd,
                                    ),
                                    child: _buildRollbackBanner(
                                      CupertinoColors.secondaryLabel
                                          .resolveFrom(context),
                                    ),
                                  ),
                                Expanded(child: _buildTextEditor(state)),
                              ],
                            ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImmersiveArticlePage(CreateEditorState state) {
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final brightness = CupertinoTheme.of(context).brightness ?? Brightness.light;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarBrightness: brightness,
        statusBarIconBrightness:
            brightness == Brightness.dark ? Brightness.light : Brightness.dark,
      ),
    );

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        // Same transparent Material host as main create route (see [AppScaffold]).
        child: Material(
          type: MaterialType.transparency,
          child: KeyedSubtree(
            key: TestKeys.createPage,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              color: background,
              child: SafeArea(
                top: false,
                bottom: false,
                child: Column(
                  children: <Widget>[
                    _buildImmersiveArticleTopBar(state: state),
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(top: AppSpacing.containerSm),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: <Widget>[
                            if (!_unifiedCreateEditorEnabled) ...<Widget>[
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

  /// 创作/沉浸文章顶栏共用：毛玻璃 + 底部分割线，并向上延伸至状态栏区域使背景连续。
  Widget _buildCreateTopChromeBar({
    required double collapseProgress,
    required Widget child,
    bool immersiveDark = false,
  }) {
    final divider = immersiveDark
        ? AppColors.white.withValues(alpha: 0.12)
        : CupertinoColors.separator.resolveFrom(context);
    final chrome = immersiveDark
        ? AppColors.black
        : CupertinoColors.systemBackground
            .resolveFrom(context)
            .withValues(alpha: lerpDouble(0.78, 0.94, collapseProgress)!);
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.only(
            top: MediaQuery.viewPaddingOf(context).top,
            left: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: chrome,
            border: Border(
              bottom: BorderSide(
                color: divider.withValues(alpha: immersiveDark ? 0.12 : 0.45),
                width: AppSpacing.hairline,
              ),
            ),
          ),
          child: SizedBox(
            height: AppSpacing.toolbarHeight,
            child: child,
          ),
        ),
      ),
    );
  }

  Widget _buildImmersiveArticleTopBar({
    required CreateEditorState state,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);

    return _buildCreateTopChromeBar(
      collapseProgress: 1,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: titleColor,
                  fontSize: AppTypography.iosNavTitle,
                  fontWeight: AppTypography.regular,
                ),
              ),
            ),
          ),
          CupertinoButton(
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
                ? CupertinoActivityIndicator(color: onAccentLabel)
                : Text(
                    UITextConstants.mediaPickerNextStep,
                    style: TextStyle(
                      color: onAccentLabel,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader({
    required CreateEditorState state,
    required double collapseProgress,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);
    return _buildCreateTopChromeBar(
      collapseProgress: collapseProgress,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Opacity(
                opacity: lerpDouble(0.34, 1, collapseProgress)!,
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.iosNavTitle,
                    fontWeight: AppTypography.regular,
                  ),
                ),
              ),
            ),
          ),
          CupertinoButton(
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
                ? CupertinoActivityIndicator(color: onAccentLabel)
                : Text(
                    UITextConstants.mediaPickerNextStep,
                    style: TextStyle(
                      color: onAccentLabel,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildTextEditor(CreateEditorState state) {
    return ArticleEditor(
      state: state,
      titleController: _titleController,
      titleFocusNode: _titleFocusNode,
      onTitleChanged: (value) {
        ref.read(createEditorProvider.notifier).updateTitle(value);
      },
      onTitleStyleChanged: (style) {
        ref.read(createEditorProvider.notifier).updateArticleTitleStyle(style);
      },
      onUpdateNodeText: (nodeId, value) {
        ref.read(createEditorProvider.notifier).updateArticleNodeText(nodeId, value);
      },
      onUpdateWrapParagraphTexts: (figureNodeId, narrowText, belowText) {
        ref.read(createEditorProvider.notifier).updateArticleWrapParagraphTexts(
              figureNodeId,
              narrowText: narrowText,
              belowText: belowText,
            );
      },
      onUpdateNodeImageLayout: (nodeId, layout) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeImageLayout(nodeId, layout);
      },
      onUpdateNodeCaption: (nodeId, caption) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeCaption(nodeId, caption);
      },
      onEditNodeImage: (nodeId) async {
        final path = ref
            .read(createEditorProvider.notifier)
            .articleNodeImageUrl(nodeId);
        if (path == null || path.trim().isEmpty || !mounted) return;
        final result = await Navigator.of(context).push<String?>(
          MaterialPageRoute<String?>(
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.createPageImagePreview,
            ),
            fullscreenDialog: true,
            builder: (_) => ImageEditorPage(
              initialPath: path,
              source: 'create',
              index: 0,
              total: 1,
              imagePaths: <String>[path],
            ),
          ),
        );
        if (!mounted || result == null || result.trim().isEmpty) return;
        ref
            .read(createEditorProvider.notifier)
            .replaceArticleNodeImage(nodeId, result.trim());
      },
      onRemoveNodeImage: (nodeId) {
        ref.read(createEditorProvider.notifier).removeArticleNode(nodeId);
      },
      onInsertImageAfter: (afterNodeId) async {
        await _pickImagesForArticleNode(afterNodeId);
      },
      onInsertImageAtSelection: (nodeId, selectionOffset) async {
        await _pickImagesForArticleTextSelection(nodeId, selectionOffset);
      },
      onActiveBlockChanged: (blockId) {
        ref.read(createEditorProvider.notifier).setActiveArticleBlock(blockId);
      },
      onInsertTextNodeAfter: (afterNodeId, {String initialText = ''}) {
        return ref.read(createEditorProvider.notifier).insertTextNodeAfter(
          afterNodeId,
          initialText: initialText,
        );
      },
      onEnsureWrapNodeGroup: (figureNodeId, {int? splitOffset}) {
        return ref.read(createEditorProvider.notifier).ensureArticleWrapNodeGroup(
              figureNodeId,
              splitOffset: splitOffset,
            );
      },
      onArticleIntrinsicImageResolved: () {
        if (mounted) setState(() {});
      },
      onPaperTextureSelected: (texture) {
        ref.read(createEditorProvider.notifier).setArticlePaperTexture(texture);
      },
      onFontSelected: (preset) {
        ref.read(createEditorProvider.notifier).setArticleFontPreset(preset);
      },
      immersive: widget.initialAction == EditorStartAction.write,
      onUndo: () => ref.read(createEditorProvider.notifier).undoArticle(),
      onRedo: () => ref.read(createEditorProvider.notifier).redoArticle(),
      canUndo: ref.read(createEditorProvider.notifier).canUndoArticle,
      canRedo: ref.read(createEditorProvider.notifier).canRedoArticle,
      onUpdateNodeType: (nodeId, type) {
        ref.read(createEditorProvider.notifier).updateArticleNodeType(nodeId, type);
      },
      onToggleInlineStyle: (nodeId, start, end, {bool? bold, bool? italic, bool? underline, bool? strikethrough}) {
        ref.read(createEditorProvider.notifier).toggleArticleInlineStyle(
          nodeId, start, end,
          bold: bold,
          italic: italic,
          underline: underline,
          strikethrough: strikethrough,
        );
      },
      onCommitTextEdit: () {
        ref.read(createEditorProvider.notifier).commitArticleTextEdit();
      },
    );
  }

  Widget _buildMediaEditor(CreateEditorState state) {
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
    required CreateEditorState state,
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
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
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ).withValues(alpha: isDark ? 0.2 : 0.04),
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
    required CreateEditorState state,
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

        final activePaths = items.toSet();
        _mediaTileBoundsKeys.removeWhere(
          (path, _) => !activePaths.contains(path),
        );

        void finishImageDragSession(String path) {
          HapticFeedback.selectionClick();
          if (!mounted) {
            return;
          }
          _applyImageReorderOnDragEnd(
            draggedPath: path,
            tileWidth: tileWidth,
            tileHeight: tileHeight,
            addEnabled: addEnabled,
          );
          setState(() {
            _draggingMediaPath = null;
            _pressedMediaPath = null;
            _imageDragLastGlobal = null;
          });
        }

        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: <Widget>[
            for (int index = 0; index < items.length; index++)
              SizedBox(
                width: tileWidth,
                child: RepaintBoundary(
                  key: _mediaTileBoundsKeyForPath(items[index]),
                  child: LongPressDraggable<String>(
                    data: items[index],
                    onDragStarted: () {
                      HapticFeedback.mediumImpact();
                      setState(() {
                        _draggingMediaPath = items[index];
                        _pressedMediaPath = items[index];
                        _imageDragLastGlobal = null;
                      });
                    },
                    onDragUpdate: (details) {
                      _imageDragLastGlobal = details.globalPosition;
                      _autoScrollDuringMediaDrag(details.globalPosition);
                    },
                    onDragEnd: (_) {
                      final dragged = _draggingMediaPath;
                      if (dragged != null) {
                        finishImageDragSession(dragged);
                      } else if (mounted) {
                        setState(() {
                          _draggingMediaPath = null;
                          _pressedMediaPath = null;
                          _imageDragLastGlobal = null;
                        });
                      }
                    },
                    onDraggableCanceled: (_, offset) {
                      _autoScrollDuringMediaDrag(offset);
                    },
                    feedback: ColoredBox(
                      color: AppColors.transparent,
                      child: Transform.scale(
                        scale: 1.06,
                        child: _buildMediaTile(
                          assetPath: items[index],
                          index: index,
                          isVideo: false,
                          width: tileWidth,
                          height: tileHeight,
                          showRemoveButton: false,
                          isEmphasized: true,
                          showFloatingShadow: true,
                          onTap: () async {},
                          onRemove: () {},
                        ),
                      ),
                    ),
                    childWhenDragging: Opacity(
                      opacity: 0.28,
                      child: _buildMediaTile(
                        assetPath: items[index],
                        index: index,
                        isVideo: false,
                        width: tileWidth,
                        height: tileHeight,
                        isPressed: _pressedMediaPath == items[index],
                        onTap: () => onTapImage(index),
                        onRemove: () => onRemove(index),
                      ),
                    ),
                    child: AnimatedOpacity(
                      duration: const Duration(milliseconds: 180),
                      opacity: _draggingMediaPath == items[index] ? 0.88 : 1,
                      child: _buildMediaTile(
                        assetPath: items[index],
                        index: index,
                        isVideo: false,
                        width: tileWidth,
                        height: tileHeight,
                        isEmphasized: false,
                        isPressed: _pressedMediaPath == items[index],
                        onTap: () => onTapImage(index),
                        onRemove: () => onRemove(index),
                      ),
                    ),
                  ),
                ),
              ),
            SizedBox(
              width: tileWidth,
              child: RepaintBoundary(
                key: _createMediaAddStripKey,
                child: _AddThumbnailButton(
                  key: TestKeys.createMediaAddButton,
                  onPressed: onAdd,
                  width: tileWidth,
                  height: tileHeight,
                  label: addLabel,
                  enabled: addEnabled,
                ),
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
    bool showRemoveButton = true,
    bool showFloatingShadow = false,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final mediaScrim = AppColorsFunctional.getColor(
      isDark,
      ColorType.createMediaOverlayBase,
    );
    final onLightContent = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final glassBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundInverse,
    );
    final deleteGlassTint = isDark
        ? AppColors.black.withValues(alpha: 0.24)
        : AppColors.iosSecondaryFill(context).withValues(alpha: 0.82);
    final deleteIconColor = AppColors.iosLabel(context);
    final deleteRingColor = AppColors.iosSeparator(
      context,
    ).withValues(alpha: 0.2);
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
                              alpha: showFloatingShadow ? 0.28 : 0.14,
                            ),
                            blurRadius: showFloatingShadow
                                ? AppSpacing.twenty
                                : AppSpacing.ten,
                            offset: Offset(
                              0,
                              showFloatingShadow
                                  ? AppSpacing.ten
                                  : AppSpacing.contentSpacingXs,
                            ),
                            spreadRadius: showFloatingShadow
                                ? AppSpacing.oneHalf
                                : 0,
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
                                  mediaScrim.withValues(
                                    alpha: isDark ? 0.14 : 0.08,
                                  ),
                                  mediaScrim.withValues(
                                    alpha: isDark ? 0.38 : 0.34,
                                  ),
                                ],
                              ),
                            ),
                          ),
                          Center(
                            child: Container(
                              width: AppSpacing.buttonHeight,
                              height: AppSpacing.buttonHeight,
                              decoration: BoxDecoration(
                                color: mediaScrim.withValues(
                                  alpha: isDark ? 0.22 : 0.28,
                                ),
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: glassBorder.withValues(
                                    alpha: isDark ? 0.2 : 0.14,
                                  ),
                                  width: AppSpacing.hairline,
                                ),
                              ),
                              child: Icon(
                                CupertinoIcons.play_fill,
                                color: onLightContent.withValues(alpha: 0.96),
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
                        errorBuilder: (context, error, stackTrace) => Container(
                          color: mediaScrim.withValues(
                            alpha: isDark ? 0.16 : 0.12,
                          ),
                        ),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        bottom: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: '编辑视频',
                          backgroundColor: mediaScrim.withValues(
                            alpha: isDark ? 0.42 : 0.48,
                          ),
                        ),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        top: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: '视频',
                          backgroundColor: mediaScrim.withValues(
                            alpha: isDark ? 0.42 : 0.48,
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
                            color: deleteGlassTint,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: deleteRingColor,
                              width: AppSpacing.hairline,
                            ),
                          ),
                          child: Icon(
                            CupertinoIcons.xmark,
                            size: AppTypography.xsPlus,
                            color: deleteIconColor,
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
    required CreateEditorState state,
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bg =
        backgroundColor ??
        mediaScrimBackdrop(isDark).withValues(alpha: isDark ? 0.42 : 0.45);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.badgeForeground);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }

  static Color mediaScrimBackdrop(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.createMediaOverlayBase);
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
    this.enabled = true,
  });

  final Future<void> Function() onPressed;
  final double width;
  final double height;
  final String label;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final accent = enabled
        ? AppColors.iosAccentLight
        : CupertinoColors.tertiaryLabel.resolveFrom(context);
    return GestureDetector(
      onTap: enabled ? () => onPressed() : null,
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
                ? AppColors.iosAccentLight.withValues(alpha: 0.24)
                : CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.18),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: enabled
                  ? AppColors.iosAccentLight.withValues(alpha: 0.06)
                  : AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundPrimary,
                    ).withValues(alpha: 0.045),
              blurRadius: AppSpacing.ten,
              offset: const Offset(0, AppSpacing.contentSpacingXs),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(CupertinoIcons.add, color: accent, size: AppSpacing.iconLarge),
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
    );
  }
}

enum _CreateMediaOption { addImages, capture, video }

class _CreatePublishConfirmSheet extends StatefulWidget {
  const _CreatePublishConfirmSheet({
    required this.initialSettings,
    required this.contentIdentity,
    required this.title,
    required this.body,
    required this.imageCount,
    required this.hasVideo,
    required this.locationService,
    required this.joinedCircles,
    required this.recommendedCircles,
  });

  final PublishSettings initialSettings;
  final CreateContentIdentity contentIdentity;
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
            title: UITextConstants.selectPublishCirclesLabel,
            value: !_settings.isPublic
                ? '仅公开内容可选'
                : _settings.circleNames.isEmpty
                ? '未选圈子'
                : _settings.circleNames.join('、'),
            onTap: _settings.isPublic ? _pickCircles : null,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          _buildSettingRow(
            context: context,
            title: UITextConstants.circlePublishModeLabel,
            value: widget.contentIdentity == CreateContentIdentity.work
                ? UITextConstants.circlePublishModeWork
                : UITextConstants.circlePublishModeMoment,
            onTap: null,
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final readBundle = postReadPreviewBundleFromPublishConfirmSummary(
      contentIdentity: widget.contentIdentity,
      title: widget.title,
      body: widget.body,
      hasVideo: widget.hasVideo,
      imageCount: widget.imageCount,
    );
    final headline = readBundle.presentation.title.trim().isNotEmpty
        ? readBundle.presentation.title
        : widget.title;
    final prose = readBundle.presentation.body.trim().isNotEmpty
        ? readBundle.presentation.body
        : widget.body;
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
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ).withValues(alpha: isDark ? 0.12 : 0.035),
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
            if (headline.isNotEmpty) ...<Widget>[
              Text(
                headline,
                style: const TextStyle(
                  fontSize: AppTypography.xl,
                  fontWeight: AppTypography.semiBold,
                  height: AppTypography.lineHeightTight,
                ),
              ),
              if (prose.isNotEmpty) SizedBox(height: AppSpacing.intraGroupXs),
            ],
            if (prose.isNotEmpty)
              _ExpandablePreviewText(
                text: prose,
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return IosSelectionOptionTile(
      title: Text(
        title,
        style: TextStyle(
          color: AppColors.iosLabel(context),
          fontSize: AppTypography.iosCallout,
          fontWeight: AppTypography.normal,
        ),
      ),
      additionalInfo: value,
      additionalInfoTextStyle: TextStyle(
        color: SettingsSemanticConstants.createSettingItemValueColor(isDark),
        fontSize: AppTypography.iosCallout,
        fontWeight: AppTypography.normal,
      ),
      showChevron: onTap != null,
      onTap: onTap,
      backgroundColor: AppColors.transparent,
      pressedColor: AppColors.iosSecondaryFill(context),
      borderRadius: borderRadius,
    );
  }

  Future<void> _pickVisibility() async {
    final nextValue = await showAppActionSheetForConfirm<bool>(
      context,
      title: context.l10n.whoCanSeeLabel,
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
      initialValue: _settings.isPublic,
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
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageLocationPicker,
        ),
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
        clearLocationPoi: option == CreateLocationOption.hidden,
        locationPoi: option == CreateLocationOption.hidden
            ? null
            : option.toLocationPoiDto(),
      );
    });
  }

  Future<void> _pickCircles() async {
    final selected = await Navigator.of(context).push<Map<String, String>>(
      CupertinoPageRoute<Map<String, String>>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPagePublishCircleSelect,
        ),
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
