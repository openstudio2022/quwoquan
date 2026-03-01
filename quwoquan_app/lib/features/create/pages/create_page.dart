import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:video_player/video_player.dart';
import 'package:video_thumbnail/video_thumbnail.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/create/components/create_entry_sheet.dart';
import 'package:quwoquan_app/features/create/models/create_media_models.dart';
import 'package:quwoquan_app/features/create/models/publish_settings_models.dart';
import 'package:quwoquan_app/features/create/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/features/create/services/publish_settings_services.dart';
import 'package:quwoquan_app/features/create/widgets/publish_circle_select_page.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

/// 创作页
///
/// 1:1 复制自 趣我圈2026/src CreatePage.tsx
/// 四 Tab moment|photo|video|article、草稿箱、退出确认、10 秒自动保存、hasContent 判断
class CreatePage extends ConsumerStatefulWidget {
  const CreatePage({super.key, this.initialType});

  final CreateEntryType? initialType;

  @override
  ConsumerState<CreatePage> createState() => _CreatePageState();
}

class _CreatePageState extends ConsumerState<CreatePage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  static const List<String> _tabIds = ['moment', 'photo', 'video', 'article'];
  static const List<String> _tabLabels = ['微趣', '美图', '视频', '文章'];
  static const List<String> _tabTitles = [
    UITextConstants.postMoment,
    UITextConstants.postPhoto,
    UITextConstants.postVideo,
    UITextConstants.postArticle,
  ];

  Map<String, dynamic> _currentData = _emptyData();
  String? _currentDraftId;
  bool _showDraftsList = false;
  bool _showExitConfirm = false;
  Timer? _autoSaveTimer;
  static const String _draftsStorageKey = 'create_drafts_list';
  static const String _currentDraftIdKey = 'create_current_draft_id';

  /// 发微趣编辑态：全屏、无一级 Tab、底部 emoji 栏、键盘弹起（图二）
  bool _isMomentEditingMode = false;

  /// 发美图编辑态：底部 TabBar 隐退（参考微趣编辑态）
  bool _isPhotoEditingMode = false;
  final FocusNode _momentFocusNode = FocusNode();

  /// 添加图片按钮焦点：进入时边框渐深，离开变回（图一）
  final FocusNode _momentAddImageFocusNode = FocusNode();

  /// 底部 emoji 面板展开时隐藏键盘、与键盘高度一致
  bool _showEmojiPanel = false;
  late final TextEditingController _momentContentController;
  static const int _kMomentMaxLength = 1000;

  /// 美图缩略图是否展开（超过 4 行时第四行之下显示“显示更多图片”，展开后全部之下显示“收起”）
  bool _photoThumbnailsExpanded = false;

  /// 创作设置行：右侧选项列固定宽度，确保三行右边缘对齐
  static const double _kTrailingColumnWidth = 140.0;

  /// 一行 5 个；4 行 = 19 缩略图 + 1 添加（参考群聊群信息更多群成员/收起）
  static const int _kPhotoThumbnailsPerRow = 5;
  static const int _kPhotoSlotsCollapsed =
      (_kPhotoThumbnailsPerRow * 4) - 1; // 19
  final PageController _photoPageController = PageController();
  final CreateLocationService _locationService = CreateLocationService();
  final CreateCircleService _circleService = const CreateCircleService();

  static Map<String, dynamic> _emptyData() {
    return {
      'moment': {
        'content': '',
        'images': <String>[],
        'visibility': 'public',
        'circleIds': <String>[],
        'circleNames': <String>[],
        'locationName': '',
        'location': <String, dynamic>{},
      },
      'photo': {
        'title': '',
        'description': '',
        'images': <String>[],
        'visibility': 'public',
        'circleIds': <String>[],
        'circleNames': <String>[],
        'locationName': '',
        'location': <String, dynamic>{},
      },
      'video': {
        'title': '',
        'description': '',
        'videoPath': '',
        'thumbnail': '',
        'durationMs': 0,
        'storyboardImages': <String>[],
        'visibility': 'public',
        'circleIds': <String>[],
        'circleNames': <String>[],
        'locationName': '',
        'location': <String, dynamic>{},
      },
      'article': {
        'title': '',
        'content': '',
        'covers': <String>[],
        'visibility': 'public',
        'circleIds': <String>[],
        'circleNames': <String>[],
        'locationName': '',
        'location': <String, dynamic>{},
      },
    };
  }

  final List<Map<String, dynamic>> _savedDrafts = [];

  void _recordCreateVisit(String tabId) {
    ref
        .read(visitRecorderServiceProvider)
        .recordVisit(VisitTarget.page('create_$tabId'));
  }

  @override
  void initState() {
    super.initState();
    _momentContentController = TextEditingController(
      text:
          (_currentData['moment'] as Map<String, dynamic>)['content']
              as String? ??
          '',
    );
    final initialIndex = _tabIndexFromType(widget.initialType);
    _tabController = TabController(
      length: _tabIds.length,
      vsync: this,
      initialIndex: initialIndex,
    );
    _loadDrafts();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _recordCreateVisit(_tabIds[_tabController.index]);
    });
    _tabController.addListener(() {
      if (_tabController.indexIsChanging) return;
      if (_tabController.index != 1 && _isPhotoEditingMode) {
        setState(() => _isPhotoEditingMode = false);
      }
      _recordCreateVisit(_tabIds[_tabController.index]);
    });
    _autoSaveTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (_hasContent()) _saveDraft();
    });
  }

  @override
  void dispose() {
    _autoSaveTimer?.cancel();
    _momentFocusNode.dispose();
    _momentAddImageFocusNode.dispose();
    _momentContentController.dispose();
    _photoPageController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  void _enterMomentEditingMode() {
    if (_tabController.index != 0) return;
    _momentAddImageFocusNode.unfocus();
    setState(() {
      _isMomentEditingMode = true;
      _showEmojiPanel = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_momentFocusNode.canRequestFocus) _momentFocusNode.requestFocus();
    });
  }

  void _exitMomentEditingMode() {
    setState(() {
      _isMomentEditingMode = false;
      _showEmojiPanel = false;
    });
    _momentFocusNode.unfocus();
    // 同步内容回 _currentData
    final content = _momentContentController.text;
    _currentData = Map.from(_currentData);
    (_currentData['moment'] as Map<String, dynamic>)['content'] = content;
  }

  void _enterPhotoEditingMode() {
    if (_tabController.index != 1) return;
    if (_isPhotoEditingMode) return;
    final photoData = _currentData['photo'] as Map<String, dynamic>? ?? {};
    final images = List<String>.from(photoData['images'] as List? ?? []);
    final currentIndex = (photoData['_photoCurrentIndex'] as int? ?? 0).clamp(
      0,
      images.isEmpty ? 0 : images.length - 1,
    );
    setState(() => _isPhotoEditingMode = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_photoPageController.hasClients) return;
      if (images.isNotEmpty) {
        _photoPageController.jumpToPage(currentIndex);
      }
    });
  }

  Future<void> _showArticleCoverOptions(bool isDark) async {
    final bg = SettingsSemanticConstants.blockBackground(isDark);
    final fg = SettingsSemanticConstants.labelColor(isDark);
    final secondary = SettingsSemanticConstants.secondaryColor(isDark);
    final selection = await showModalBottomSheet<int>(
      context: context,
      backgroundColor: bg,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                title: Text(
                  UITextConstants.articleCoverOptionNone,
                  style: TextStyle(color: fg),
                ),
                subtitle: Text(
                  UITextConstants.articleCoverOptionNoneDesc,
                  style: TextStyle(color: secondary),
                ),
                onTap: () => Navigator.of(context).pop(0),
              ),
              ListTile(
                title: Text(
                  UITextConstants.articleCoverOptionOne,
                  style: TextStyle(color: fg),
                ),
                onTap: () => Navigator.of(context).pop(1),
              ),
              ListTile(
                title: Text(
                  UITextConstants.articleCoverOptionTwo,
                  style: TextStyle(color: fg),
                ),
                onTap: () => Navigator.of(context).pop(2),
              ),
              ListTile(
                title: Text(
                  UITextConstants.articleCoverOptionThree,
                  style: TextStyle(color: fg),
                ),
                onTap: () => Navigator.of(context).pop(3),
              ),
            ],
          ),
        );
      },
    );
    if (!mounted || selection == null) return;
    if (selection == 0) {
      setState(() {
        _currentData = Map.from(_currentData);
        (_currentData['article'] as Map<String, dynamic>)['covers'] =
            <String>[];
      });
      return;
    }
    final currentCovers = List<String>.from(
      ((_currentData['article'] as Map<String, dynamic>?)?['covers']
              as List?) ??
          <String>[],
    );
    final paths = await _pickImages(
      maxCount: selection,
      initialPaths: currentCovers,
    );
    if (!mounted) return;
    setState(() {
      _currentData = Map.from(_currentData);
      (_currentData['article'] as Map<String, dynamic>)['covers'] = paths;
    });
  }

  /// 发表微趣：发布到云侧内容服务，成功后退出编辑态并提示
  Future<void> _publishMoment() async {
    final content = _momentContentController.text;
    _currentData = Map.from(_currentData);
    (_currentData['moment'] as Map<String, dynamic>)['content'] = content;
    final payload = _buildPostPayload('moment');
    if (payload == null) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.loadFailed)));
      }
      return;
    }
    try {
      final dataService = ref.read(dataServiceProvider);
      await dataService.createDataItem(endpoint: '/posts', data: payload);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.loadFailed)));
      }
      return;
    }
    if (_currentDraftId != null) {
      final nextDrafts = _savedDrafts
          .where((e) => e['id'] != _currentDraftId)
          .toList();
      setState(() {
        _savedDrafts
          ..clear()
          ..addAll(nextDrafts);
        _currentDraftId = null;
      });
      _persistDrafts(nextDrafts, null);
    }
    _exitMomentEditingMode();
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(UITextConstants.momentPublished)));
      _doClose();
    }
  }

  Future<void> _publishCurrentTab() async {
    final tab = _tabIds[_tabController.index];
    final payload = _buildPostPayload(tab);
    if (payload == null) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.loadFailed)));
      }
      return;
    }
    try {
      final dataService = ref.read(dataServiceProvider);
      await dataService.createDataItem(endpoint: '/posts', data: payload);
      if (_currentDraftId != null) {
        final nextDrafts = _savedDrafts
            .where((e) => e['id'] != _currentDraftId)
            .toList();
        setState(() {
          _savedDrafts
            ..clear()
            ..addAll(nextDrafts);
          _currentDraftId = null;
        });
        await _persistDrafts(nextDrafts, null);
      }
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(UITextConstants.momentPublished)));
      _doClose();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.loadFailed)));
    }
  }

  Map<String, dynamic>? _buildPostPayload(String tab) {
    final publishFields = _buildPublishPayloadFields(tab);
    switch (tab) {
      case 'moment':
        final d = _currentData['moment'] as Map<String, dynamic>? ?? {};
        return <String, dynamic>{
          'contentType': 'micro',
          'body': (d['content'] as String? ?? '').trim(),
          'mediaUrls': List<String>.from(d['images'] as List? ?? <String>[]),
          'title': '',
          'tags': <String>[],
          ...publishFields,
        };
      case 'photo':
        final d = _currentData['photo'] as Map<String, dynamic>? ?? {};
        return <String, dynamic>{
          'contentType': 'image',
          'title': (d['title'] as String? ?? '').trim(),
          'body': (d['description'] as String? ?? '').trim(),
          'mediaUrls': List<String>.from(d['images'] as List? ?? <String>[]),
          'tags': <String>[],
          ...publishFields,
        };
      case 'video':
        final d = _currentData['video'] as Map<String, dynamic>? ?? {};
        final videoPath = (d['videoPath'] as String? ?? '').trim();
        final mediaUrls = <String>[if (videoPath.isNotEmpty) videoPath];
        return <String, dynamic>{
          'contentType': 'video',
          'title': (d['title'] as String? ?? '').trim(),
          'body': (d['description'] as String? ?? '').trim(),
          'videoUrl': videoPath,
          'mediaUrls': mediaUrls,
          'coverUrl': (d['thumbnail'] as String? ?? '').trim(),
          'tags': <String>[],
          ...publishFields,
        };
      case 'article':
        final d = _currentData['article'] as Map<String, dynamic>? ?? {};
        final covers = List<String>.from(d['covers'] as List? ?? <String>[]);
        return <String, dynamic>{
          'contentType': 'article',
          'title': (d['title'] as String? ?? '').trim(),
          'body': (d['content'] as String? ?? '').trim(),
          'coverUrl': covers.isNotEmpty ? covers.first : '',
          'mediaUrls': covers,
          'tags': <String>[],
          ...publishFields,
        };
      default:
        return null;
    }
  }

  Map<String, dynamic> _tabData(String tab) {
    final data =
        _currentData[tab] as Map<String, dynamic>? ?? <String, dynamic>{};
    if (!data.containsKey('visibility')) data['visibility'] = 'public';
    if (!data.containsKey('circleIds')) data['circleIds'] = <String>[];
    if (!data.containsKey('circleNames')) data['circleNames'] = <String>[];
    if (!data.containsKey('locationName')) data['locationName'] = '';
    if (!data.containsKey('location')) data['location'] = <String, dynamic>{};
    return data;
  }

  bool _isPublic(String tab) =>
      (_tabData(tab)['visibility']?.toString() ?? 'public').toLowerCase() ==
      'public';

  String _locationDisplay(String tab, AppLocalizations l10n) {
    final name = (_tabData(tab)['locationName'] as String? ?? '').trim();
    return name.isEmpty ? l10n.locationHidden : name;
  }

  String _circlesDisplay(String tab, AppLocalizations l10n) {
    final names = List<String>.from(
      _tabData(tab)['circleNames'] as List? ?? const <String>[],
    );
    if (names.isEmpty) return l10n.noCirclesAvailable;
    return names.join(', ');
  }

  Map<String, dynamic> _buildPublishPayloadFields(String tab) {
    return PublishSettings.fromMap(_tabData(tab)).toPayloadFields();
  }

  int _tabIndexFromType(CreateEntryType? type) {
    if (type == null) return 0;
    switch (type) {
      case CreateEntryType.weiquPhoto:
      case CreateEntryType.weiquText:
      case CreateEntryType.weiquVideo:
        return 0;
      case CreateEntryType.zuopinImage:
        return 1;
      case CreateEntryType.zuopinVideo:
        return 2;
      case CreateEntryType.zuopinArticle:
        return 3;
    }
  }

  /// 发微趣时是否有内容可发表（有文字或图片则可点发表）
  bool get _canPublishMoment {
    final d = _currentData['moment'] as Map<String, dynamic>? ?? {};
    return (d['content'] as String? ?? '').trim().isNotEmpty ||
        (d['images'] as List?)?.isNotEmpty == true;
  }

  bool _hasContent() {
    final tab = _tabIds[_tabController.index];
    final d = _currentData[tab] as Map<String, dynamic>? ?? {};
    switch (tab) {
      case 'moment':
        return (d['content'] as String? ?? '').isNotEmpty ||
            (d['images'] as List?)?.isNotEmpty == true;
      case 'photo':
        return (d['title'] as String? ?? '').isNotEmpty ||
            (d['images'] as List?)?.isNotEmpty == true;
      case 'video':
        return (d['title'] as String? ?? '').isNotEmpty ||
            (d['videoPath'] as String? ?? '').isNotEmpty ||
            (d['thumbnail'] as String? ?? '').isNotEmpty ||
            (d['storyboardImages'] as List?)?.isNotEmpty == true;
      case 'article':
        return (d['title'] as String? ?? '').isNotEmpty ||
            (d['content'] as String? ?? '').isNotEmpty ||
            (d['covers'] as List?)?.isNotEmpty == true ||
            (d['cover'] as String? ?? '').isNotEmpty;
      default:
        return false;
    }
  }

  Future<void> _loadDrafts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_draftsStorageKey);
    if (raw == null || raw.isEmpty) return;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is List) {
        final drafts = decoded
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        if (!mounted) return;
        setState(() {
          _savedDrafts
            ..clear()
            ..addAll(drafts);
          // 不恢复 currentDraftId：每次进入创作页视为新会话，保存时新增草稿；只有从草稿箱点选才绑定并覆盖该条
          _currentDraftId = null;
        });
      }
    } catch (_) {
      // ignore malformed local cache
    }
  }

  Future<void> _persistDrafts(
    List<Map<String, dynamic>> drafts,
    String? currentId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_draftsStorageKey, jsonEncode(drafts));
    if (currentId == null) {
      await prefs.remove(_currentDraftIdKey);
    } else {
      await prefs.setString(_currentDraftIdKey, currentId);
    }
  }

  void _saveDraft() {
    final tab = _tabIds[_tabController.index];
    final dataToSave = _currentData[tab];
    final now = DateTime.now().millisecondsSinceEpoch;
    final nextDrafts = List<Map<String, dynamic>>.from(_savedDrafts);
    String? nextId = _currentDraftId;
    if (nextId != null) {
      final idx = nextDrafts.indexWhere((e) => e['id'] == nextId);
      if (idx >= 0) {
        nextDrafts[idx] = {
          ...nextDrafts[idx],
          'updatedAt': now,
          'data': dataToSave,
        };
      } else {
        nextId = null;
      }
    }
    if (nextId == null) {
      nextId = now.toString();
      nextDrafts.insert(0, {
        'id': nextId,
        'type': tab,
        'updatedAt': now,
        'data': dataToSave,
      });
    }
    setState(() {
      _savedDrafts
        ..clear()
        ..addAll(nextDrafts);
      _currentDraftId = nextId;
    });
    _persistDrafts(nextDrafts, nextId);
  }

  void _onCloseRequest() {
    if (_hasContent()) {
      setState(() => _showExitConfirm = true);
    } else {
      _doClose();
    }
  }

  void _doClose() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/');
    }
  }

  void _handleSaveAndExit() {
    _saveDraft();
    setState(() => _showExitConfirm = false);
    _doClose();
  }

  void _handleDiscardAndExit() {
    if (_currentDraftId != null) {
      final nextDrafts = _savedDrafts
          .where((e) => e['id'] != _currentDraftId)
          .toList();
      setState(() {
        _savedDrafts
          ..clear()
          ..addAll(nextDrafts);
        _currentDraftId = null;
      });
      _persistDrafts(nextDrafts, null);
    }
    setState(() => _showExitConfirm = false);
    _doClose();
  }

  void _handleRestoreDraft(Map<String, dynamic> draft) {
    final tab = draft['type'] as String? ?? 'moment';
    final idx = _tabIds.indexOf(tab);
    if (idx >= 0) _tabController.animateTo(idx);
    final restored = (draft['data'] as Map<String, dynamic>?) ?? {};
    setState(() {
      final newData = _emptyData();
      newData[tab] = restored;
      _currentData = newData;
      _currentDraftId = draft['id'] as String?;
      _showDraftsList = false;
      _isMomentEditingMode = false;
      _showEmojiPanel = false;
      _isPhotoEditingMode = false;
    });
    final moment = _currentData['moment'] as Map<String, dynamic>?;
    _momentContentController.text = moment?['content'] as String? ?? '';
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (tab == 'moment') {
        _enterMomentEditingMode();
      } else if (tab == 'photo') {
        _enterPhotoEditingMode();
      }
    });
    _persistDrafts(_savedDrafts, _currentDraftId);
  }

  void _handleDeleteDraft(String id) {
    final nextDrafts = _savedDrafts.where((e) => e['id'] != id).toList();
    final nextId = _currentDraftId == id ? null : _currentDraftId;
    setState(() {
      _savedDrafts
        ..clear()
        ..addAll(nextDrafts);
      _currentDraftId = nextId;
    });
    _persistDrafts(nextDrafts, nextId);
  }

  /// 发表按钮：AppBar 内紧凑样式（高度小、上下间距小）。无内容时 [enabled]==false 为浅色不可点。
  Widget _buildPublishButton({
    required bool isDark,
    required VoidCallback onPressed,
    String? label,
    bool enabled = true,
  }) {
    final text = label ?? UITextConstants.publish;
    final bg = enabled
        ? SettingsSemanticConstants.actionButtonPrimaryBackground
        : SettingsSemanticConstants.actionButtonDisabledBackground(isDark);
    final fg = enabled
        ? SettingsSemanticConstants.actionButtonPrimaryForeground
        : SettingsSemanticConstants.actionButtonDisabledForeground(isDark);
    return Padding(
      padding: EdgeInsets.only(right: AppSpacing.sm),
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.actionButtonBorderRadius,
        ),
        child: InkWell(
          onTap: enabled ? onPressed : null,
          borderRadius: BorderRadius.circular(
            SettingsSemanticConstants.actionButtonBorderRadius,
          ),
          child: SizedBox(
            height: SettingsSemanticConstants.actionButtonHeightInToolbar,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: SettingsSemanticConstants
                    .actionButtonPaddingHorizontalInToolbar,
                vertical: SettingsSemanticConstants
                    .actionButtonPaddingVerticalInToolbar,
              ),
              child: Center(
                child: Text(
                  text,
                  style: TextStyle(
                    fontSize:
                        SettingsSemanticConstants.actionButtonTextSizeInToolbar,
                    fontWeight: FontWeight.w600,
                    color: fg,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<CreateMediaPickerResult?> _openCreateMediaPicker({
    required MediaPickerEntryMode mode,
    required int maxSelection,
    List<String> initialPaths = const <String>[],
  }) {
    final initialSelection = initialPaths
        .where((path) => path.trim().isNotEmpty)
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
        .take(maxSelection)
        .toList();
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

  /// 打开创作媒体选择器并返回图片路径列表（微趣/美图/文章共用）
  Future<List<String>> _pickImages({
    int maxCount = 9,
    List<String> initialPaths = const <String>[],
  }) async {
    final result = await _openCreateMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: maxCount,
      initialPaths: initialPaths,
    );
    if (!mounted || result == null) return <String>[];
    final imagePaths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(maxCount)
        .toList();
    if (result.openOneTapMovie) {
      _applyOneTapMovieSelection(result.items);
      return imagePaths;
    }
    return imagePaths;
  }

  void _applyOneTapMovieSelection(List<CreateMediaItem> items) {
    final imagePaths = items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .toList();
    if (imagePaths.isEmpty) return;
    setState(() {
      _currentData = Map.from(_currentData);
      final video = Map<String, dynamic>.from(
        _currentData['video'] as Map<String, dynamic>? ?? <String, dynamic>{},
      );
      video['storyboardImages'] = imagePaths;
      _currentData['video'] = video;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(UITextConstants.mediaPickerOneTapMovieQueued)),
    );
  }

  /// 打开创作媒体选择器并返回视频路径（发视频使用）
  Future<String?> _pickVideo() async {
    final currentVideo =
        (_currentData['video'] as Map<String, dynamic>?)?['videoPath']
            ?.toString() ??
        '';
    final result = await _openCreateMediaPicker(
      mode: MediaPickerEntryMode.video,
      maxSelection: 1,
      initialPaths: currentVideo.isEmpty
          ? const <String>[]
          : <String>[currentVideo],
    );
    if (!mounted || result == null || result.items.isEmpty) return null;
    final firstVideo = result.items.firstWhere(
      (item) => item.isVideo,
      orElse: () => result.items.first,
    );
    return firstVideo.path;
  }

  bool _isVideoFilePath(String path) {
    final lower = path.toLowerCase();
    return lower.endsWith('.mp4') ||
        lower.endsWith('.mov') ||
        lower.endsWith('.m4v') ||
        lower.endsWith('.avi') ||
        lower.endsWith('.mkv') ||
        lower.endsWith('.webm');
  }

  Future<Duration?> _getVideoDuration(String path) async {
    try {
      final controller = VideoPlayerController.file(File(path));
      await controller.initialize();
      final duration = controller.value.duration;
      await controller.dispose();
      return duration;
    } catch (_) {
      return null;
    }
  }

  Future<String?> _generateVideoThumbnail(String path) async {
    try {
      final dir = await getTemporaryDirectory();
      return await VideoThumbnail.thumbnailFile(
        video: path,
        thumbnailPath: dir.path,
        imageFormat: ImageFormat.PNG,
        quality: 75,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> _handlePickVideo() async {
    final path = await _pickVideo();
    if (path == null || !mounted) return;
    final duration = await _getVideoDuration(path);
    if (!mounted) return;
    if (duration != null && duration > const Duration(hours: 1)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.videoDurationTooLong)),
      );
      return;
    }
    final thumb = await _generateVideoThumbnail(path);
    if (!mounted) return;
    setState(() {
      _currentData = Map.from(_currentData);
      (_currentData['video'] as Map)['videoPath'] = path;
      (_currentData['video'] as Map)['thumbnail'] = thumb ?? '';
      (_currentData['video'] as Map)['durationMs'] =
          duration?.inMilliseconds ?? 0;
      (_currentData['video'] as Map)['storyboardImages'] = <String>[];
    });
  }

  /// 打开图片编辑页（重建后三段式编辑器），返回编辑后的路径（String）或多图时 {index, path}（Map）
  Future<Object?> _openEditImage(
    String source,
    String path,
    int index, {
    int total = 1,
    List<String>? allPaths,
  }) async {
    if (path.isEmpty) return null;
    final params = <String, String>{
      'path': path,
      'source': source,
      'index': '$index',
      'total': '$total',
    };
    final paths = allPaths ?? (path.isNotEmpty ? [path] : <String>[]);
    for (var i = 0; i < paths.length; i++) {
      params['path$i'] = paths[i];
    }
    final uri = Uri(path: '/create/edit-image', queryParameters: params);
    return context.push<Object>(uri.toString());
  }

  ({int index, String path})? _parseEditImageResult(
    Object? result,
    int fallbackIndex,
  ) {
    if (result == null) return null;
    if (result is String && result.isNotEmpty) {
      return (index: fallbackIndex, path: result);
    }
    if (result is Map) {
      final path = result['path']?.toString() ?? '';
      if (path.isEmpty) return null;
      final rawIndex = result['index'];
      final parsedIndex = rawIndex is int
          ? rawIndex
          : int.tryParse(rawIndex?.toString() ?? '');
      return (index: parsedIndex ?? fallbackIndex, path: path);
    }
    return null;
  }

  void _applyEditedImageToTab({
    required String tabKey,
    required int fallbackIndex,
    required Object? result,
  }) {
    final parsed = _parseEditImageResult(result, fallbackIndex);
    if (parsed == null) return;
    setState(() {
      _currentData = Map.from(_currentData);
      final tab = Map<String, dynamic>.from(
        _currentData[tabKey] as Map<String, dynamic>? ?? {},
      );
      final list = List<String>.from(tab['images'] as List? ?? []);
      if (list.isEmpty) return;
      final safeIndex = parsed.index.clamp(0, list.length - 1);
      list[safeIndex] = parsed.path;
      tab['images'] = list;
      if (tabKey == 'photo') {
        tab['_photoCurrentIndex'] = safeIndex;
      }
      _currentData[tabKey] = tab;
    });
  }

  Future<void> _openPhotoImageEditorAt(int index) async {
    final photoData = _currentData['photo'] as Map<String, dynamic>? ?? {};
    final images = List<String>.from(photoData['images'] as List? ?? []);
    if (images.isEmpty || index < 0 || index >= images.length) return;
    final result = await _openEditImage(
      'photo',
      images[index],
      index,
      total: images.length,
      allPaths: images,
    );
    if (!mounted) return;
    _applyEditedImageToTab(
      tabKey: 'photo',
      fallbackIndex: index,
      result: result,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.createPageBackground(isDark);
    final blockSurface = SettingsSemanticConstants.createPageBlockBackground(
      isDark,
    );
    final fgColor = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final hasContent = _hasContent();

    return Stack(
      children: [
        Scaffold(
          backgroundColor: pageBg,
          appBar: AppBar(
            backgroundColor: blockSurface,
            elevation: 0,
            scrolledUnderElevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.close),
              onPressed: _onCloseRequest,
            ),
            title: ListenableBuilder(
              listenable: _tabController,
              builder: (context, _) {
                return Text(
                  _tabTitles[_tabController.index],
                  style: TextStyle(
                    color: fgColor,
                    fontSize:
                        SettingsSemanticConstants.createToolbarTitleFontSize,
                    fontWeight: FontWeight.normal,
                  ),
                );
              },
            ),
            centerTitle: true,
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(1),
              child: Container(
                height: 1,
                color: SettingsSemanticConstants.dividerColor(isDark),
              ),
            ),
            actions: [
              if (_isMomentEditingMode)
                _buildPublishButton(
                  isDark: isDark,
                  onPressed: () {
                    _publishMoment();
                  },
                  enabled: _canPublishMoment,
                )
              else if (hasContent)
                _buildPublishButton(
                  isDark: isDark,
                  onPressed: () {
                    _publishCurrentTab();
                  },
                  label: _tabController.index == 0
                      ? UITextConstants.publish
                      : UITextConstants.publishAction,
                )
              else
                TextButton.icon(
                  onPressed: () => setState(() => _showDraftsList = true),
                  icon: Icon(
                    Icons.inventory_2_outlined,
                    size: AppSpacing.iconMedium,
                    color: fgSecondary,
                  ),
                  label: Text(
                    UITextConstants.drafts,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: fgSecondary,
                    ),
                  ),
                ),
            ],
          ),
          body: Column(
            children: [
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  physics: _isPhotoEditingMode
                      ? const NeverScrollableScrollPhysics()
                      : null,
                  children: _tabIds.asMap().entries.map((e) {
                    return _buildEditorPlaceholder(
                      context,
                      e.key,
                      isDark,
                      fgColor,
                      fgSecondary,
                    );
                  }).toList(),
                ),
              ),
              if (_isMomentEditingMode)
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    GestureDetector(
                      onTap: () {
                        setState(() {
                          _showEmojiPanel = !_showEmojiPanel;
                          if (_showEmojiPanel) {
                            _momentFocusNode.unfocus();
                          } else {
                            _momentFocusNode.requestFocus();
                          }
                        });
                      },
                      child: Container(
                        height:
                            SettingsSemanticConstants.toolbarHeightOverKeyboard,
                        width: double.infinity,
                        padding: EdgeInsets.symmetric(
                          horizontal:
                              SettingsSemanticConstants.blockHorizontalPadding,
                          vertical:
                              (SettingsSemanticConstants
                                      .toolbarHeightOverKeyboard -
                                  SettingsSemanticConstants
                                      .createToolbarIconSize) /
                              2,
                        ),
                        decoration: BoxDecoration(
                          color: blockSurface,
                          border: Border(
                            top: BorderSide(
                              color: SettingsSemanticConstants.dividerColor(
                                isDark,
                              ),
                            ),
                          ),
                        ),
                        child: SafeArea(
                          top: false,
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: Icon(
                              _showEmojiPanel
                                  ? Icons.keyboard_outlined
                                  : Icons.emoji_emotions_outlined,
                              color: fgColor,
                              size: SettingsSemanticConstants
                                  .createToolbarIconSize,
                            ),
                          ),
                        ),
                      ),
                    ),
                    if (_showEmojiPanel)
                      UnifiedEmojiPicker(
                        onEmojiSelected: (char) {
                          final t = _momentContentController;
                          final pos = t.selection.baseOffset.clamp(
                            0,
                            t.text.length,
                          );
                          t.text =
                              t.text.substring(0, pos) +
                              char +
                              t.text.substring(pos);
                          t.selection = TextSelection.collapsed(
                            offset: pos + char.length,
                          );
                          setState(() {
                            _currentData = Map.from(_currentData);
                            (_currentData['moment']
                                    as Map<String, dynamic>)['content'] =
                                t.text;
                          });
                        },
                      ),
                  ],
                )
              else if (_isPhotoEditingMode)
                const SizedBox.shrink()
              else
                Container(
                  decoration: BoxDecoration(
                    color: blockSurface,
                    border: Border(
                      top: BorderSide(
                        color: SettingsSemanticConstants.dividerColor(isDark),
                      ),
                    ),
                  ),
                  child: SafeArea(
                    top: false,
                    child: TabBar(
                      controller: _tabController,
                      indicator: const BoxDecoration(),
                      indicatorSize: TabBarIndicatorSize.tab,
                      dividerHeight: 0,
                      labelColor: fgColor,
                      unselectedLabelColor: fgSecondary,
                      labelStyle: TextStyle(
                        fontSize: SettingsSemanticConstants
                            .createToolbarTitleFontSize,
                        fontWeight: FontWeight.w600,
                        color: fgColor,
                      ),
                      unselectedLabelStyle: TextStyle(
                        fontSize: SettingsSemanticConstants
                            .createToolbarTitleFontSize,
                        fontWeight: FontWeight.normal,
                        color: fgSecondary,
                      ),
                      tabs: _tabLabels.map((l) => Tab(text: l)).toList(),
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (_showExitConfirm) _buildExitConfirm(isDark, fgColor, fgSecondary),
        if (_showDraftsList) _buildDraftsList(isDark, fgColor, fgSecondary),
      ],
    );
  }

  /// 1:1 结构对应 CreatePage.tsx：发微趣为文字+图片一体块、带状分割、三选项块
  Widget _buildEditorPlaceholder(
    BuildContext context,
    int tabIndex,
    bool isDark,
    Color fgColor,
    Color fgSecondary,
  ) {
    final tabId = _tabIds[tabIndex];
    final data = _currentData[tabId] as Map<String, dynamic>? ?? {};
    final blockSurface = SettingsSemanticConstants.createPageBlockBackground(
      isDark,
    );
    final blockBorderColor = SettingsSemanticConstants.blockBorderColor(isDark);
    final blockDecoration = BoxDecoration(
      color: blockSurface,
      borderRadius: BorderRadius.circular(
        SettingsSemanticConstants.blockBorderRadius,
      ),
      border: Border.all(color: blockBorderColor),
    );
    final blockSpacing = SettingsSemanticConstants.blockSpacing;
    final blockPad = SettingsSemanticConstants.blockHorizontalPadding;

    if (tabId == 'moment') {
      final momentBlocks = _buildMomentFields(
        data,
        fgColor,
        fgSecondary,
        isDark: isDark,
        focusNode: _momentFocusNode,
        onEnterEditing: _enterMomentEditingMode,
        addImageFocusNode: _momentAddImageFocusNode,
      );
      final textBlock = momentBlocks[0];
      final mediaBlock = momentBlocks.length >= 3 ? momentBlocks[2] : null;
      final hintBlock = momentBlocks.length >= 6 ? momentBlocks[3] : null;
      final optionsBlock = momentBlocks.length >= 5 ? momentBlocks.last : null;
      final momentContentChildren = <Widget>[
        textBlock,
        Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.sectionVerticalPadding - 4,
          ),
          child: Divider(
            height: 1,
            thickness: SettingsSemanticConstants.dividerThickness,
            color: SettingsSemanticConstants.createInlineDividerColor(isDark),
          ),
        ),
      ];
      if (mediaBlock != null) {
        momentContentChildren.add(mediaBlock);
      }
      if (hintBlock != null) {
        momentContentChildren.add(hintBlock);
      }
      return SingleChildScrollView(
        padding: EdgeInsets.only(
          left: 0,
          right: 0,
          top: SettingsSemanticConstants.createContentTopPadding,
          bottom: blockSpacing,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: double.infinity,
              decoration: blockDecoration,
              padding: EdgeInsets.all(blockPad),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: momentContentChildren,
              ),
            ),
            if (optionsBlock != null) ...[
              SizedBox(
                height: SettingsSemanticConstants.createStripSeparatorHeight,
              ),
              Container(
                width: double.infinity,
                decoration: blockDecoration,
                padding: EdgeInsets.zero,
                child: optionsBlock,
              ),
            ],
          ],
        ),
      );
    }

    if (tabId == 'photo') {
      final photoBlocks = _buildPhotoFields(data, fgColor, fgSecondary, isDark);
      return SingleChildScrollView(
        padding: EdgeInsets.only(
          left: 0,
          right: 0,
          top: SettingsSemanticConstants.createContentTopPadding,
          bottom: blockSpacing,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: photoBlocks.asMap().entries.map((e) {
            return Padding(
              padding: EdgeInsets.only(bottom: blockSpacing),
              child: Container(
                width: double.infinity,
                decoration: blockDecoration,
                padding: e.key == photoBlocks.length - 1
                    ? EdgeInsets.zero
                    : EdgeInsets.all(blockPad),
                child: e.value,
              ),
            );
          }).toList(),
        ),
      );
    }

    if (tabId == 'video') {
      final videoBlocks = _buildVideoFields(data, fgColor, fgSecondary, isDark);
      return SingleChildScrollView(
        padding: EdgeInsets.only(
          left: 0,
          right: 0,
          top: SettingsSemanticConstants.createContentTopPadding,
          bottom: blockSpacing,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: videoBlocks.asMap().entries.map((e) {
            return Padding(
              padding: EdgeInsets.only(bottom: blockSpacing),
              child: Container(
                width: double.infinity,
                decoration: blockDecoration,
                padding: e.key == videoBlocks.length - 1
                    ? EdgeInsets.zero
                    : EdgeInsets.all(blockPad),
                child: e.value,
              ),
            );
          }).toList(),
        ),
      );
    }

    if (tabId == 'article') {
      final articleBlocks = _buildArticleFields(
        data,
        fgColor,
        fgSecondary,
        isDark,
      );
      return SingleChildScrollView(
        padding: EdgeInsets.only(
          left: 0,
          right: 0,
          top: SettingsSemanticConstants.createContentTopPadding,
          bottom: blockSpacing,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: articleBlocks.asMap().entries.map((e) {
            return Padding(
              padding: EdgeInsets.only(bottom: blockSpacing),
              child: Container(
                width: double.infinity,
                decoration: blockDecoration,
                padding: e.key == articleBlocks.length - 1
                    ? EdgeInsets.zero
                    : EdgeInsets.all(blockPad),
                child: e.value,
              ),
            );
          }).toList(),
        ),
      );
    }

    return SingleChildScrollView(
      padding: EdgeInsets.all(blockPad),
      child: Container(
        width: double.infinity,
        decoration: blockDecoration,
        padding: EdgeInsets.all(blockPad),
        child: const SizedBox.shrink(),
      ),
    );
  }

  /// MomentEditorCard 1:1（图一）：白块、分割线、字数在输入区内、添加图焦点边框、拖动排序
  List<Widget> _buildMomentFields(
    Map<String, dynamic> data,
    Color fgColor,
    Color fgSecondary, {
    required bool isDark,
    FocusNode? focusNode,
    VoidCallback? onEnterEditing,
    FocusNode? addImageFocusNode,
  }) {
    final images = List<String>.from(data['images'] as List? ?? []);
    return [
      // 1. 文本输入区 + 字数在输入区内显示（非工具栏底）
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextFormField(
            controller: _momentContentController,
            focusNode: focusNode,
            decoration: InputDecoration(
              hintText: UITextConstants.momentPlaceholder,
              hintStyle: TextStyle(
                color: SettingsSemanticConstants.createInputHintColor(isDark),
                fontSize: SettingsSemanticConstants.createInputMomentFontSize,
              ),
              border: InputBorder.none,
              filled: false,
              contentPadding: EdgeInsets.zero,
              counterText: '',
            ),
            style: TextStyle(
              color: fgColor,
              fontSize: SettingsSemanticConstants.createInputMomentFontSize,
            ),
            maxLines: 4,
            minLines: 2,
            maxLength: _kMomentMaxLength,
            onTap: onEnterEditing,
            onChanged: (v) => setState(() {
              _currentData = Map.from(_currentData);
              (_currentData['moment'] as Map<String, dynamic>)['content'] = v;
            }),
            contextMenuBuilder: (context, editableTextState) {
              final items = editableTextState.contextMenuButtonItems.where((
                item,
              ) {
                final label = item.label?.toLowerCase() ?? '';
                return !label.contains('scan') && !label.contains('扫描');
              }).toList();
              return AdaptiveTextSelectionToolbar.buttonItems(
                anchors: editableTextState.contextMenuAnchors,
                buttonItems: items,
              );
            },
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Align(
            alignment: Alignment.centerRight,
            child: Text(
              '${_momentContentController.text.length}/$_kMomentMaxLength',
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            ),
          ),
        ],
      ),
      // 文字与图片区间隔两行（一空行一待输入）
      SizedBox(height: AppSpacing.interGroupXl),
      // 2. 媒体区：可拖动排序、添加格焦点时边框渐深
      LayoutBuilder(
        builder: (context, constraints) {
          final gap = AppSpacing.interGroupXs;
          final cellSize = (constraints.maxWidth - gap * 2) / 3;
          final totalCells = images.length + 1;
          final rowCount = (totalCells / 3).ceil();
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(rowCount, (row) {
              return Padding(
                padding: EdgeInsets.only(bottom: row < rowCount - 1 ? gap : 0),
                child: Row(
                  children: List.generate(3, (col) {
                    final index = row * 3 + col;
                    if (index >= totalCells) {
                      return SizedBox(width: cellSize, height: cellSize);
                    }
                    if (index == images.length) {
                      return Padding(
                        padding: EdgeInsets.only(right: col < 2 ? gap : 0),
                        child: GestureDetector(
                          onTap: () async {
                            addImageFocusNode?.requestFocus();
                            onEnterEditing?.call();
                            final paths = await _pickImages(
                              maxCount: 9,
                              initialPaths: images,
                            );
                            if (paths.isEmpty) return;
                            final oldLength = images.length;
                            setState(() {
                              _currentData = Map.from(_currentData);
                              (_currentData['moment'] as Map)['images'] = paths;
                            });
                            if (!mounted) return;
                            final merged = List<String>.from(
                              (_currentData['moment'] as Map)['images']
                                      as List? ??
                                  [],
                            );
                            if (merged.isEmpty) return;
                            final targetIndex = oldLength.clamp(
                              0,
                              merged.length - 1,
                            );
                            final result = await _openEditImage(
                              'moment',
                              merged[targetIndex],
                              targetIndex,
                              total: merged.length,
                              allPaths: merged,
                            );
                            if (!mounted) return;
                            _applyEditedImageToTab(
                              tabKey: 'moment',
                              fallbackIndex: targetIndex,
                              result: result,
                            );
                          },
                          child: _buildDashedAddTile(
                            isDark: isDark,
                            width: cellSize,
                            height: cellSize,
                            borderRadius: SettingsSemanticConstants
                                .createAddTileBorderRadius,
                            child: Icon(
                              Icons.add,
                              size: AppSpacing.iconLarge + AppSpacing.iconSmall,
                              color:
                                  SettingsSemanticConstants.createAddTileIconColor(
                                    isDark,
                                  ),
                            ),
                          ),
                        ),
                      );
                    }
                    final path = images[index];
                    return Padding(
                      padding: EdgeInsets.only(right: col < 2 ? gap : 0),
                      child: _buildMomentDraggableImageCell(
                        key: ValueKey(path),
                        path: path,
                        index: index,
                        cellSize: cellSize,
                        images: images,
                        fgSecondary: fgSecondary,
                        onEnterEditing: onEnterEditing,
                      ),
                    );
                  }),
                ),
              );
            }),
          );
        },
      ),
      if (images.isNotEmpty)
        Padding(
          padding: EdgeInsets.only(top: AppSpacing.interGroupXs),
          child: Text(
            UITextConstants.momentImageReorderHint,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: fgSecondary.withValues(alpha: 0.9),
            ),
          ),
        ),
      SizedBox(height: AppSpacing.interGroupLg),
      _buildPublishSettingsSection(
        tabKey: 'moment',
        fgColor: fgColor,
        fgSecondary: fgSecondary,
        isDark: isDark,
      ),
    ];
  }

  Widget _createOptionDivider(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.xs / 2),
      child: Divider(
        height: 1,
        thickness: SettingsSemanticConstants.dividerThickness,
        color: SettingsSemanticConstants.dividerColor(isDark),
      ),
    );
  }

  Widget _buildPublishSettingsSection({
    required String tabKey,
    required Color fgColor,
    required Color fgSecondary,
    required bool isDark,
  }) {
    final l10n = context.l10n;
    final locationText = _locationDisplay(tabKey, l10n);
    final isPublic = _isPublic(tabKey);
    final circlesText = _circlesDisplay(tabKey, l10n);
    final blue = AppColors.primaryColor;
    final isLocationSelected = locationText != l10n.locationHidden;

    return Column(
      children: [
        _momentListTile(
          icon: CupertinoIcons.location,
          label: l10n.locationLabel,
          trailing: locationText,
          trailingColor: isLocationSelected
              ? blue
              : SettingsSemanticConstants.createSettingItemValueColor(isDark),
          fgColor: fgColor,
          fgSecondary: fgSecondary,
          isDark: isDark,
          onTap: () => _selectLocation(tabKey),
        ),
        _createOptionDivider(isDark),
        _momentListTile(
          icon: CupertinoIcons.globe,
          label: l10n.isPublicLabel,
          fgColor: fgColor,
          fgSecondary: fgSecondary,
          isDark: isDark,
          showChevron: false,
          trailingWidget: CupertinoSwitch(
            value: isPublic,
            activeTrackColor: blue,
            onChanged: (next) {
              setState(() {
                final nextData = Map<String, dynamic>.from(_tabData(tabKey));
                nextData['visibility'] = next ? 'public' : 'private';
                if (!next) {
                  nextData['circleIds'] = <String>[];
                  nextData['circleNames'] = <String>[];
                }
                _currentData = Map<String, dynamic>.from(_currentData)
                  ..[tabKey] = nextData;
              });
            },
          ),
          onTap: () {
            setState(() {
              final nextPublic = !_isPublic(tabKey);
              final nextData = Map<String, dynamic>.from(_tabData(tabKey));
              nextData['visibility'] = nextPublic ? 'public' : 'private';
              if (!nextPublic) {
                nextData['circleIds'] = <String>[];
                nextData['circleNames'] = <String>[];
              }
              _currentData = Map<String, dynamic>.from(_currentData)
                ..[tabKey] = nextData;
            });
          },
        ),
        if (isPublic) ...[
          _createOptionDivider(isDark),
          _momentListTile(
            icon: CupertinoIcons.person_2,
            label: l10n.selectPublishCirclesLabel,
            trailing: circlesText,
            trailingColor: circlesText == l10n.noCirclesAvailable
                ? SettingsSemanticConstants.createSettingItemValueColor(isDark)
                : blue,
            fgColor: fgColor,
            fgSecondary: fgSecondary,
            isDark: isDark,
            onTap: () => _selectCircles(tabKey),
          ),
        ],
      ],
    );
  }

  Future<void> _selectLocation(String tabKey) async {
    final result = await Navigator.of(context).push<CreateLocationOption>(
      CupertinoPageRoute<CreateLocationOption>(
        builder: (context) =>
            PublishLocationSelectorPage(locationService: _locationService),
      ),
    );
    if (!mounted || result == null) return;
    setState(() {
      final nextData = Map<String, dynamic>.from(_tabData(tabKey));
      if (result.name.isEmpty) {
        nextData['locationName'] = '';
        nextData['location'] = <String, dynamic>{};
      } else {
        nextData['locationName'] = result.name;
        nextData['location'] = result.toLocationMap();
      }
      _currentData = Map<String, dynamic>.from(_currentData)
        ..[tabKey] = nextData;
    });
  }

  Future<void> _selectCircles(String tabKey) async {
    final dataService = ref.read(dataServiceProvider);
    final joinedCircles = await _circleService.listCircles(dataService);
    if (!mounted) return;
    final selectedIds = List<String>.from(
      _tabData(tabKey)['circleIds'] as List? ?? const <String>[],
    );
    final selectedNames = List<String>.from(
      _tabData(tabKey)['circleNames'] as List? ?? const <String>[],
    );
    final selected = <String, String>{};
    if (selectedIds.isEmpty && joinedCircles.isNotEmpty) {
      for (final c in joinedCircles) {
        selected[c.id] = c.name;
      }
    } else {
      for (var i = 0; i < selectedIds.length; i++) {
        selected[selectedIds[i]] = i < selectedNames.length
            ? selectedNames[i]
            : selectedIds[i];
      }
    }
    final result = await Navigator.of(context).push<Map<String, String>>(
      CupertinoPageRoute<Map<String, String>>(
        fullscreenDialog: true,
        builder: (context) => PublishCircleSelectPage(
          joinedCircles: joinedCircles,
          initialSelected: selected,
          recommendedCircles: mockRecommendedCircles,
        ),
      ),
    );
    if (!mounted || result == null) return;
    setState(() {
      final nextData = Map<String, dynamic>.from(_tabData(tabKey));
      nextData['circleIds'] = result.keys.toList();
      nextData['circleNames'] = result.values.toList();
      _currentData = Map<String, dynamic>.from(_currentData)
        ..[tabKey] = nextData;
    });
  }

  Widget _momentListTile({
    required IconData icon,
    required String label,
    required Color fgColor,
    required Color fgSecondary,
    required bool isDark,
    String? trailing,
    Color? trailingColor,
    Widget? trailingWidget,
    bool showChevron = true,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: SettingsSemanticConstants.blockHorizontalPadding,
          vertical: SettingsSemanticConstants.sectionVerticalPadding,
        ),
        child: Row(
          children: [
            Icon(icon, size: AppSpacing.iconMedium, color: fgColor),
            SizedBox(width: AppSpacing.interGroupSm),
            Expanded(
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      label,
                      style: TextStyle(
                        fontSize: SettingsSemanticConstants
                            .createSettingItemLabelFontSize,
                        fontWeight: FontWeight.normal,
                        color: fgColor,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  SizedBox(width: AppSpacing.interGroupSm),
                  SizedBox(
                    width: _kTrailingColumnWidth,
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          ...? (trailingWidget != null ? [trailingWidget] : null),
                          if (trailing != null)
                            Flexible(
                              child: Text(
                                trailing,
                                style: TextStyle(
                                  fontSize: SettingsSemanticConstants
                                      .createSettingItemValueFontSize,
                                  color:
                                      trailingColor ??
                                      SettingsSemanticConstants.createSettingItemValueColor(
                                        isDark,
                                      ),
                                ),
                                overflow: TextOverflow.ellipsis,
                                textAlign: TextAlign.end,
                              ),
                            ),
                          if (showChevron) ...[
                            SizedBox(width: AppSpacing.interGroupXs),
                            Icon(
                              CupertinoIcons.chevron_forward,
                              size: AppSpacing.iconMedium,
                              color: fgSecondary,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 发微趣媒体区：可拖动排序的图片格（长按拖拽，动效由 Draggable 默认提供）
  Widget _buildMomentDraggableImageCell({
    required Key key,
    required String path,
    required int index,
    required double cellSize,
    required List<String> images,
    required Color fgSecondary,
    VoidCallback? onEnterEditing,
  }) {
    return LongPressDraggable<int>(
      data: index,
      delay: const Duration(milliseconds: 200),
      feedback: Material(
        elevation: AppSpacing.intraGroupMd,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: SizedBox(
          width: cellSize,
          height: cellSize,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            child: _photoImage(path, fgSecondary),
          ),
        ),
      ),
      childWhenDragging: Opacity(
        opacity: 0.4,
        child: SizedBox(
          width: cellSize,
          height: cellSize,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            child: _photoImage(path, fgSecondary),
          ),
        ),
      ),
      child: DragTarget<int>(
        onAcceptWithDetails: (details) {
          final from = details.data;
          if (from == index) return;
          setState(() {
            _currentData = Map.from(_currentData);
            final list = List<String>.from(
              (_currentData['moment'] as Map)['images'] as List? ?? [],
            );
            if (from < 0 ||
                from >= list.length ||
                index < 0 ||
                index >= list.length) {
              return;
            }
            final a = list[from];
            list[from] = list[index];
            list[index] = a;
            (_currentData['moment'] as Map)['images'] = list;
          });
        },
        builder: (context, candidateData, rejectedData) {
          final isDragTarget = candidateData.isNotEmpty;
          return AnimatedScale(
            scale: isDragTarget ? 1.08 : 1.0,
            duration: const Duration(milliseconds: 120),
            curve: Curves.easeOut,
            child: Container(
              width: cellSize,
              height: cellSize,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: GestureDetector(
                onTap: () async {
                  onEnterEditing?.call();
                  final result = await _openEditImage(
                    'moment',
                    path,
                    index,
                    total: images.length,
                    allPaths: images,
                  );
                  if (!mounted) return;
                  _applyEditedImageToTab(
                    tabKey: 'moment',
                    fallbackIndex: index,
                    result: result,
                  );
                },
                child: _momentImageCell(
                  path,
                  onRemove: () {
                    setState(() {
                      _currentData = Map.from(_currentData);
                      final list = List<String>.from(
                        (_currentData['moment'] as Map)['images'] as List? ??
                            [],
                      );
                      list.removeAt(index);
                      (_currentData['moment'] as Map)['images'] = list;
                    });
                  },
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  /// 发微趣媒体区：与添加格同大的图片格，仅删除按钮；点击整格由外层打开编辑页，无编辑笔（原型：小字提示点击编辑）
  Widget _momentImageCell(String path, {required VoidCallback onRemove}) {
    final isFilePath =
        path.startsWith('/') ||
        (path.length > 1 && path[1] == ':' && path.length > 2);
    final image = isFilePath
        ? Image.file(
            File(path),
            fit: BoxFit.cover,
            errorBuilder: (context, error, stackTrace) => Container(
              color: AppColorsFunctional.getColor(
                ref.read(isDarkProvider),
                ColorType.backgroundSecondary,
              ),
            ),
          )
        : Image.network(
            path,
            fit: BoxFit.cover,
            errorBuilder: (context, error, stackTrace) => Container(
              color: AppColorsFunctional.getColor(
                ref.read(isDarkProvider),
                ColorType.backgroundSecondary,
              ),
            ),
          );
    return Stack(
      fit: StackFit.expand,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          child: image,
        ),
        Positioned(
          top: AppSpacing.xs,
          right: AppSpacing.xs,
          child: GestureDetector(
            onTap: onRemove,
            child: CircleAvatar(
              radius: AppSpacing.sm + AppSpacing.xs / 2,
              backgroundColor: Colors.black54,
              child: Icon(
                Icons.close,
                size: AppSpacing.iconSmall,
                color: Colors.white,
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// UnifiedImagePostCard：添加图片+标题配文一体块 / 三选项（无分割条）
  static const int _kMaxPhotoImages = 30;

  List<Widget> _buildPhotoFields(
    Map<String, dynamic> data,
    Color fgColor,
    Color fgSecondary,
    bool isDark,
  ) {
    final images = List<String>.from(data['images'] as List? ?? []);
    final currentIndex = images.isEmpty
        ? 0
        : (data['_photoCurrentIndex'] as int? ?? 0).clamp(0, images.length - 1);

    final blockBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );

    final imageBlock = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        AspectRatio(
          aspectRatio: 4 / 3,
          child: Container(
            decoration: BoxDecoration(
              color: blockBg,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              child: images.isEmpty
                  ? GestureDetector(
                      onTap: () async {
                        final paths = await _pickImages(
                          maxCount: _kMaxPhotoImages,
                          initialPaths: images,
                        );
                        if (paths.isEmpty) return;
                        final oldLength = images.length;
                        setState(() {
                          _currentData = Map.from(_currentData);
                          (_currentData['photo'] as Map)['images'] = paths;
                        });
                        if (!mounted) return;
                        final list = List<String>.from(
                          (_currentData['photo'] as Map)['images'] as List? ??
                              [],
                        );
                        if (list.isEmpty) return;
                        final targetIndex = oldLength.clamp(0, list.length - 1);
                        final result = await _openEditImage(
                          'photo',
                          list[targetIndex],
                          targetIndex,
                          total: list.length,
                          allPaths: list,
                        );
                        if (!mounted) return;
                        _applyEditedImageToTab(
                          tabKey: 'photo',
                          fallbackIndex: targetIndex,
                          result: result,
                        );
                        _enterPhotoEditingMode();
                      },
                      child: _buildDashedAddTile(
                        isDark: isDark,
                        borderRadius: AppSpacing.largeBorderRadius,
                        child: Icon(
                          Icons.add,
                          size: AppSpacing.largeButtonSize,
                          color:
                              SettingsSemanticConstants.createAddTileIconColor(
                                isDark,
                              ),
                        ),
                      ),
                    )
                  : _buildPhotoMainImageStack(
                      images: images,
                      currentIndex: currentIndex,
                      data: data,
                      fgSecondary: fgSecondary,
                    ),
            ),
          ),
        ),
        if (images.isNotEmpty) ...[
          SizedBox(height: AppSpacing.interGroupXs),
          _buildPhotoThumbnailGrid(
            images: images,
            currentIndex: currentIndex,
            data: data,
            fgColor: fgColor,
            fgSecondary: fgSecondary,
            isDark: isDark,
            blockBg: blockBg,
          ),
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: Text(
              UITextConstants.photoReorderHint,
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            ),
          ),
        ],
      ],
    );
    final titleDescBlock = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        TextFormField(
          initialValue: data['title'] as String? ?? '',
          onTap: _enterPhotoEditingMode,
          decoration: InputDecoration(
            hintText: UITextConstants.photoTitleHint,
            hintStyle: TextStyle(
              color: SettingsSemanticConstants.createInputHintColor(isDark),
              fontSize: SettingsSemanticConstants.createInputTitleFontSize,
            ),
            border: InputBorder.none,
            contentPadding: EdgeInsets.zero,
          ),
          style: TextStyle(
            color: fgColor,
            fontSize: SettingsSemanticConstants.createInputTitleFontSize,
            fontWeight: FontWeight.bold,
          ),
          onChanged: (v) {
            _enterPhotoEditingMode();
            setState(() {
              _currentData = Map.from(_currentData);
              (_currentData['photo'] as Map<String, dynamic>)['title'] = v;
            });
          },
        ),
        Padding(
          padding: EdgeInsets.only(top: 8),
          child: TextFormField(
            initialValue: data['description'] as String? ?? '',
            onTap: _enterPhotoEditingMode,
            decoration: InputDecoration(
              hintText: UITextConstants.photoBodyHint,
              hintStyle: TextStyle(
                color: SettingsSemanticConstants.createInputHintColor(isDark),
                fontSize: SettingsSemanticConstants.createInputBodyFontSize,
              ),
              border: InputBorder.none,
              contentPadding: EdgeInsets.zero,
            ),
            style: TextStyle(
              color: fgColor,
              fontSize: SettingsSemanticConstants.createInputBodyFontSize,
            ),
            maxLines: 2,
            onChanged: (v) {
              _enterPhotoEditingMode();
              setState(() {
                _currentData = Map.from(_currentData);
                (_currentData['photo'] as Map<String, dynamic>)['description'] =
                    v;
              });
            },
          ),
        ),
      ],
    );
    return [
      // 1. 添加图片 + 标题配文一体（无分割条）
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          imageBlock,
          Padding(padding: EdgeInsets.only(top: 8), child: titleDescBlock),
        ],
      ),
      _buildPublishSettingsSection(
        tabKey: 'photo',
        fgColor: fgColor,
        fgSecondary: fgSecondary,
        isDark: isDark,
      ),
    ];
  }

  Widget _buildPhotoMainImageStack({
    required List<String> images,
    required int currentIndex,
    required Map<String, dynamic> data,
    required Color fgSecondary,
  }) {
    if (_isPhotoEditingMode && images.length > 1) {
      return Stack(
        fit: StackFit.expand,
        children: [
          PageView.builder(
            controller: _photoPageController,
            itemCount: images.length,
            onPageChanged: (index) {
              setState(() {
                _currentData = Map.from(_currentData);
                (_currentData['photo'] as Map)['_photoCurrentIndex'] = index;
              });
            },
            itemBuilder: (context, index) {
              return GestureDetector(
                onTap: () => _openPhotoImageEditorAt(index),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  child: _photoImage(images[index], fgSecondary),
                ),
              );
            },
          ),
          Positioned(
            top: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupLg,
                vertical: AppSpacing.intraGroupXs,
              ),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
              ),
              child: Text(
                '${currentIndex + 1} / ${images.length}',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: AppTypography.sm,
                ),
              ),
            ),
          ),
          Positioned(
            top: AppSpacing.containerSm,
            left: AppSpacing.containerSm,
            child: GestureDetector(
              onTap: () {
                setState(() {
                  _currentData = Map.from(_currentData);
                  final list = List<String>.from(
                    (_currentData['photo'] as Map)['images'] as List? ?? [],
                  );
                  list.removeAt(currentIndex);
                  (_currentData['photo'] as Map)['images'] = list;
                  int next = (data['_photoCurrentIndex'] as int? ?? 0);
                  if (next >= list.length) {
                    next = list.isNotEmpty ? list.length - 1 : 0;
                  }
                  (_currentData['photo'] as Map)['_photoCurrentIndex'] = next;
                });
              },
              child: CircleAvatar(
                radius: AppSpacing.iconButtonMinSizeSm / 2,
                backgroundColor: Colors.black54,
                child: Icon(
                  Icons.close,
                  size: AppSpacing.iconMedium,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ],
      );
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(
          child: GestureDetector(
            onTap: () {
              _enterPhotoEditingMode();
              _openPhotoImageEditorAt(currentIndex);
            },
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              child: _photoImage(images[currentIndex], fgSecondary),
            ),
          ),
        ),
        if (images.length > 1)
          Positioned(
            top: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupLg,
                vertical: AppSpacing.intraGroupXs,
              ),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
              ),
              child: Text(
                '${currentIndex + 1} / ${images.length}',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: AppTypography.sm,
                ),
              ),
            ),
          ),
        Positioned(
          top: AppSpacing.containerSm,
          left: AppSpacing.containerSm,
          child: GestureDetector(
            onTap: () {
              setState(() {
                _currentData = Map.from(_currentData);
                final list = List<String>.from(
                  (_currentData['photo'] as Map)['images'] as List? ?? [],
                );
                list.removeAt(currentIndex);
                (_currentData['photo'] as Map)['images'] = list;
                int next = (data['_photoCurrentIndex'] as int? ?? 0);
                if (next >= list.length) {
                  next = list.isNotEmpty ? list.length - 1 : 0;
                }
                (_currentData['photo'] as Map)['_photoCurrentIndex'] = next;
              });
            },
            child: CircleAvatar(
              radius: AppSpacing.iconButtonMinSizeSm / 2,
              backgroundColor: Colors.black54,
              child: Icon(
                Icons.close,
                size: AppSpacing.iconMedium,
                color: Colors.white,
              ),
            ),
          ),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          top: 0,
          child: IgnorePointer(
            child: Center(
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                  vertical: AppSpacing.intraGroupMd,
                ),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
                ),
                child: Text(
                  UITextConstants.photoTapToEdit,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: AppTypography.base,
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// 美图缩略图网格：4 行 × 5 列，最后一格为添加按钮；超过 19 张第四行之下显示“显示更多图片”，展开后全部之下显示“收起”（参考群信息更多群成员/收起）
  Widget _buildPhotoThumbnailGrid({
    required List<String> images,
    required int currentIndex,
    required Map<String, dynamic> data,
    required Color fgSecondary,
    required Color fgColor,
    required bool isDark,
    required Color blockBg,
  }) {
    const gap = 8.0;
    final crossCount = _kPhotoThumbnailsPerRow;
    final visibleCount =
        images.length > _kPhotoSlotsCollapsed && !_photoThumbnailsExpanded
        ? _kPhotoSlotsCollapsed
        : images.length;
    final showMoreOrCollapse = images.length > _kPhotoSlotsCollapsed;

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final cellW = (width - gap * (crossCount - 1)) / crossCount;
        final size = cellW.clamp(48.0, 72.0);

        Widget cellThumbnail(int index) {
          final path = images[index];
          final isCurrent = index == currentIndex;
          return LongPressDraggable<int>(
            data: index,
            delay: const Duration(milliseconds: 200),
            feedback: Material(
              elevation: AppSpacing.intraGroupXs,
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              child: SizedBox(
                width: size,
                height: size,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  child: _photoImage(path, fgSecondary),
                ),
              ),
            ),
            childWhenDragging: Opacity(
              opacity: 0.4,
              child: SizedBox(
                width: size,
                height: size,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  child: _photoImage(path, fgSecondary),
                ),
              ),
            ),
            child: DragTarget<int>(
              onAcceptWithDetails: (details) {
                final from = details.data;
                if (from == index) return;
                setState(() {
                  _currentData = Map.from(_currentData);
                  final list = List<String>.from(
                    (_currentData['photo'] as Map)['images'] as List? ?? [],
                  );
                  if (from < 0 ||
                      from >= list.length ||
                      index < 0 ||
                      index >= list.length) {
                    return;
                  }
                  final a = list[from];
                  list[from] = list[index];
                  list[index] = a;
                  (_currentData['photo'] as Map)['images'] = list;
                  final cur = (data['_photoCurrentIndex'] as int? ?? 0);
                  if (cur == from) {
                    (_currentData['photo'] as Map)['_photoCurrentIndex'] =
                        index;
                  } else if (cur == index) {
                    (_currentData['photo'] as Map)['_photoCurrentIndex'] = from;
                  }
                });
              },
              builder: (context, candidateData, rejectedData) {
                final isDragTarget = candidateData.isNotEmpty;
                return AnimatedScale(
                  scale: isDragTarget ? 1.08 : 1.0,
                  duration: const Duration(milliseconds: 120),
                  curve: Curves.easeOut,
                  child: Container(
                    width: size,
                    height: size,
                    decoration: BoxDecoration(
                      color: blockBg,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.borderRadius,
                      ),
                      border: Border.all(
                        color: isCurrent
                            ? AppColors.primaryColor
                            : fgSecondary.withValues(alpha: 0.2),
                        width: isCurrent
                            ? AppSpacing.toolPanelItemBorderWidthSelected
                            : AppSpacing.toolPanelItemBorderWidthUnselected,
                      ),
                    ),
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () => setState(() {
                          _currentData = Map.from(_currentData);
                          (_currentData['photo'] as Map)['_photoCurrentIndex'] =
                              index;
                        }),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius + AppSpacing.xs / 2,
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.smallBorderRadius + AppSpacing.xs / 2,
                          ),
                          child: _photoImage(path, fgSecondary),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        }

        final cells = <Widget>[];
        for (var i = 0; i < visibleCount; i++) {
          cells.add(cellThumbnail(i));
        }
        if (images.length < _kMaxPhotoImages) {
          cells.add(
            GestureDetector(
              onTap: () async {
                final paths = await _pickImages(
                  maxCount: _kMaxPhotoImages,
                  initialPaths: images,
                );
                if (paths.isEmpty) return;
                final oldLength = images.length;
                setState(() {
                  _currentData = Map.from(_currentData);
                  (_currentData['photo'] as Map)['images'] = paths;
                });
                if (!mounted) return;
                final merged = List<String>.from(
                  (_currentData['photo'] as Map)['images'] as List? ?? [],
                );
                if (merged.isEmpty) return;
                final targetIndex = oldLength.clamp(0, merged.length - 1);
                final result = await _openEditImage(
                  'photo',
                  merged[targetIndex],
                  targetIndex,
                  total: merged.length,
                  allPaths: merged,
                );
                if (!mounted) return;
                _applyEditedImageToTab(
                  tabKey: 'photo',
                  fallbackIndex: targetIndex,
                  result: result,
                );
                _enterPhotoEditingMode();
              },
              child: _buildDashedAddTile(
                isDark: isDark,
                width: size,
                height: size,
                borderRadius:
                    SettingsSemanticConstants.createAddTileBorderRadius,
                child: Icon(
                  Icons.add,
                  color: SettingsSemanticConstants.createAddTileIconColor(
                    isDark,
                  ),
                  size: AppSpacing.iconLarge - AppSpacing.xs,
                ),
              ),
            ),
          );
        }

        final rowCount = (cells.length / crossCount).ceil();
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ...List.generate(rowCount, (row) {
              return Padding(
                padding: EdgeInsets.only(bottom: row < rowCount - 1 ? gap : 0),
                child: Row(
                  children: List.generate(crossCount, (col) {
                    final idx = row * crossCount + col;
                    if (idx >= cells.length) {
                      return SizedBox(width: size, height: size);
                    }
                    return Padding(
                      padding: EdgeInsets.only(
                        right: col < crossCount - 1 ? gap : 0,
                      ),
                      child: cells[idx],
                    );
                  }),
                ),
              );
            }),
            if (showMoreOrCollapse) ...[
              SizedBox(height: AppSpacing.xs),
              Center(
                child: GestureDetector(
                  onTap: () => setState(
                    () => _photoThumbnailsExpanded = !_photoThumbnailsExpanded,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _photoThumbnailsExpanded
                            ? UITextConstants.photoCollapseLabel
                            : UITextConstants.photoShowMorePictures,
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgColor.withValues(alpha: 0.75),
                        ),
                      ),
                      SizedBox(width: AppSpacing.xs),
                      Icon(
                        _photoThumbnailsExpanded
                            ? Icons.keyboard_arrow_up
                            : Icons.keyboard_arrow_down,
                        size: AppSpacing.iconMedium,
                        color: fgColor.withValues(alpha: 0.75),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        );
      },
    );
  }

  Widget _photoImage(String path, Color fgSecondary) {
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
    final errorBg = Colors.white;
    if (isFile) {
      return Image.file(
        File(path),
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => Container(
          color: errorBg,
          child: Icon(
            Icons.broken_image_outlined,
            color: fgSecondary.withValues(alpha: 0.5),
          ),
        ),
      );
    }
    return Image.network(
      path,
      fit: BoxFit.cover,
      errorBuilder: (context, error, stackTrace) => Container(
        color: errorBg,
        child: Icon(
          Icons.broken_image_outlined,
          color: fgSecondary.withValues(alpha: 0.5),
        ),
      ),
    );
  }

  Widget _buildVideoPlaceholder(Color fgSecondary) {
    return Container(
      color: fgSecondary.withValues(alpha: 0.08),
      child: Center(
        child: Icon(
          Icons.play_circle_outline,
          size: AppSpacing.bottomNavHeight,
          color: fgSecondary.withValues(alpha: 0.6),
        ),
      ),
    );
  }

  Widget _buildDashedAddTile({
    required bool isDark,
    required Widget child,
    double? width,
    double? height,
    double? borderRadius,
  }) {
    final radius =
        borderRadius ?? SettingsSemanticConstants.createAddTileBorderRadius;
    final bg = SettingsSemanticConstants.createAddTileBackground(isDark);
    final border = SettingsSemanticConstants.createAddTileBorderColor(isDark);
    Widget content = CustomPaint(
      painter: _DashedBorderPainter(
        color: border,
        strokeWidth: SettingsSemanticConstants.createAddTileBorderWidth,
        dashLength: SettingsSemanticConstants.createAddTileDashLength,
        dashGap: SettingsSemanticConstants.createAddTileDashGap,
        radius: radius,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
        ),
        child: Center(child: child),
      ),
    );
    if (width == null && height == null) {
      return LayoutBuilder(
        builder: (context, constraints) {
          return SizedBox(
            width: constraints.maxWidth,
            height: constraints.maxHeight,
            child: content,
          );
        },
      );
    }
    return SizedBox(width: width, height: height, child: content);
  }

  /// VideoEditorCard：上传区+标题描述一体块 / 三选项（与美图添加图片背景一致，无分割条）
  List<Widget> _buildVideoFields(
    Map<String, dynamic> data,
    Color fgColor,
    Color fgSecondary,
    bool isDark,
  ) {
    final blockBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final rawVideo = data['videoPath'] as String? ?? '';
    final rawThumb = data['thumbnail'] as String? ?? '';
    final storyboardImages = List<String>.from(
      data['storyboardImages'] as List? ?? const <String>[],
    );
    final legacyVideo = rawVideo.isEmpty && _isVideoFilePath(rawThumb)
        ? rawThumb
        : '';
    final videoPath = rawVideo.isNotEmpty ? rawVideo : legacyVideo;
    final thumb = rawVideo.isNotEmpty
        ? rawThumb
        : (legacyVideo.isNotEmpty ? '' : rawThumb);
    final hasVideo = videoPath.isNotEmpty;
    final hasStoryboard = storyboardImages.isNotEmpty;
    final uploadBlock = AspectRatio(
      aspectRatio: 4 / 3,
      child: Container(
        decoration: BoxDecoration(
          color: blockBg,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: hasVideo
            ? Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                    child: thumb.isNotEmpty
                        ? _photoImage(thumb, fgSecondary)
                        : _buildVideoPlaceholder(fgSecondary),
                  ),
                  Center(
                    child: Container(
                      width: AppSpacing.bottomNavHeight + AppSpacing.sm,
                      height: AppSpacing.bottomNavHeight + AppSpacing.sm,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.9),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(color: Colors.black12, blurRadius: 8),
                        ],
                      ),
                      child: Icon(
                        Icons.play_arrow,
                        size: AppSpacing.iconLarge + AppSpacing.xs,
                        color: Colors.black87,
                      ),
                    ),
                  ),
                  Positioned(
                    bottom: AppSpacing.containerSm,
                    right: AppSpacing.containerSm,
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupMd,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius,
                        ),
                      ),
                      child: Text(
                        '00:00',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: AppTypography.sm,
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: AppSpacing.containerSm,
                    right: AppSpacing.containerSm,
                    child: TextButton(
                      onPressed: _handlePickVideo,
                      child: Text(
                        UITextConstants.videoChangeCover,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: AppTypography.sm,
                        ),
                      ),
                    ),
                  ),
                ],
              )
            : GestureDetector(
                onTap: _handlePickVideo,
                child: _buildDashedAddTile(
                  isDark: isDark,
                  borderRadius: 12,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        hasStoryboard
                            ? Icons.movie_creation_outlined
                            : Icons.upload_outlined,
                        size: AppSpacing.iconLarge,
                        color: SettingsSemanticConstants.createAddTileIconColor(
                          isDark,
                        ),
                      ),
                      SizedBox(height: AppSpacing.interGroupSm),
                      Text(
                        hasStoryboard
                            ? '${UITextConstants.mediaPickerOneTapMovie} (${storyboardImages.length})'
                            : UITextConstants.videoUploadLabel,
                        style: TextStyle(
                          fontSize:
                              SettingsSemanticConstants.createInputBodyFontSize,
                          fontWeight: FontWeight.w500,
                          color:
                              SettingsSemanticConstants.createAddTileIconColor(
                                isDark,
                              ),
                        ),
                      ),
                      if (hasStoryboard) ...[
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.mediaPickerOneTapMovieQueued,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color:
                                SettingsSemanticConstants.createAddTileIconColor(
                                  isDark,
                                ),
                          ),
                        ),
                      ] else if (UITextConstants
                          .videoUploadHint
                          .isNotEmpty) ...[
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.videoUploadHint,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color:
                                SettingsSemanticConstants.createAddTileIconColor(
                                  isDark,
                                ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
      ),
    );
    final titleDescBlock = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        TextFormField(
          initialValue: data['title'] as String? ?? '',
          decoration: InputDecoration(
            hintText: UITextConstants.videoTitlePlaceholder,
            hintStyle: TextStyle(
              color: SettingsSemanticConstants.createInputHintColor(isDark),
              fontSize: SettingsSemanticConstants.createInputTitleFontSize,
            ),
            border: InputBorder.none,
            contentPadding: EdgeInsets.zero,
          ),
          style: TextStyle(
            color: fgColor,
            fontSize: SettingsSemanticConstants.createInputTitleFontSize,
            fontWeight: FontWeight.bold,
          ),
          onChanged: (v) => setState(() {
            _currentData = Map.from(_currentData);
            (_currentData['video'] as Map<String, dynamic>)['title'] = v;
          }),
        ),
        Padding(
          padding: EdgeInsets.only(top: 8),
          child: TextFormField(
            initialValue: data['description'] as String? ?? '',
            decoration: InputDecoration(
              hintText: UITextConstants.videoDescPlaceholder,
              hintStyle: TextStyle(
                color: SettingsSemanticConstants.createInputHintColor(isDark),
                fontSize: SettingsSemanticConstants.createInputBodyFontSize,
              ),
              border: InputBorder.none,
              contentPadding: EdgeInsets.zero,
            ),
            style: TextStyle(
              color: fgColor,
              fontSize: SettingsSemanticConstants.createInputBodyFontSize,
            ),
            maxLines: 2,
            onChanged: (v) => setState(() {
              _currentData = Map.from(_currentData);
              (_currentData['video'] as Map<String, dynamic>)['description'] =
                  v;
            }),
          ),
        ),
      ],
    );
    return [
      // 1. 上传区 + 标题描述一体（无分割条）
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          uploadBlock,
          Padding(padding: EdgeInsets.only(top: 8), child: titleDescBlock),
        ],
      ),
      _buildPublishSettingsSection(
        tabKey: 'video',
        fgColor: fgColor,
        fgSecondary: fgSecondary,
        isDark: isDark,
      ),
    ];
  }

  /// ArticleEditorCard 1:1：封面在前、标题+正文同块、三选项
  List<Widget> _buildArticleFields(
    Map<String, dynamic> data,
    Color fgColor,
    Color fgSecondary,
    bool isDark,
  ) {
    final covers = List<String>.from(data['covers'] as List? ?? []);
    final legacyCover = data['cover'] as String? ?? '';
    if (covers.isEmpty && legacyCover.isNotEmpty) {
      covers.add(legacyCover);
    }
    final titleText = (data['title'] as String? ?? '').trim();
    final titleDisplay = titleText.isEmpty
        ? UITextConstants.articleTitlePlaceholder
        : titleText;
    final titleColor = titleText.isEmpty
        ? SettingsSemanticConstants.createInputHintColor(isDark)
        : fgColor;

    Widget buildCoverImage(String path) {
      final isFilePath =
          path.isNotEmpty &&
          (path.startsWith('/') || (path.length > 1 && path[1] == ':'));
      return ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: isFilePath
            ? Image.file(
                File(path),
                fit: BoxFit.cover,
                errorBuilder: (ctx, error, stackTrace) => Center(
                  child: Text(
                    ctx.l10n.loadFailed,
                    style: TextStyle(color: fgSecondary),
                  ),
                ),
              )
            : Image.network(
                path,
                fit: BoxFit.cover,
                errorBuilder: (ctx, error, stackTrace) => Center(
                  child: Text(
                    ctx.l10n.loadFailed,
                    style: TextStyle(color: fgSecondary),
                  ),
                ),
              ),
      );
    }

    Widget coverPreview;
    if (covers.isEmpty) {
      coverPreview = _buildDashedAddTile(
        isDark: isDark,
        height: 120,
        borderRadius: AppSpacing.largeBorderRadius,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.add,
              size: AppSpacing.iconLarge - AppSpacing.xs,
              color: SettingsSemanticConstants.createAddTileIconColor(isDark),
            ),
            SizedBox(height: AppSpacing.interGroupXs),
            Text(
              UITextConstants.addCover,
              style: TextStyle(
                color: SettingsSemanticConstants.createAddTileIconColor(isDark),
              ),
            ),
          ],
        ),
      );
    } else if (covers.length == 1) {
      coverPreview = Row(
        children: [
          Expanded(
            child: Text(
              titleDisplay,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: SettingsSemanticConstants.createInputTitleFontSize,
                fontWeight: FontWeight.bold,
                color: titleColor,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          SizedBox(
            width: AppSpacing.buttonHeight * 2.5,
            height: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
            child: buildCoverImage(covers.first),
          ),
        ],
      );
    } else {
      final rowCovers = covers.take(3).toList();
      coverPreview = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            titleDisplay,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: SettingsSemanticConstants.createInputTitleFontSize,
              fontWeight: FontWeight.bold,
              color: titleColor,
            ),
          ),
          SizedBox(height: AppSpacing.interGroupXs),
          Row(
            children: List.generate(rowCovers.length, (i) {
              return Expanded(
                child: Padding(
                  padding: EdgeInsets.only(
                    right: i < rowCovers.length - 1
                        ? AppSpacing.interGroupXs
                        : 0,
                  ),
                  child: AspectRatio(
                    aspectRatio: 4 / 3,
                    child: buildCoverImage(rowCovers[i]),
                  ),
                ),
              );
            }),
          ),
        ],
      );
    }

    return [
      // 1. 封面（支持 1-3 图）
      GestureDetector(
        onTap: () async {
          await _showArticleCoverOptions(isDark);
        },
        child: coverPreview,
      ),
      // 2. 标题 + 正文（同一功能块）
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          TextFormField(
            initialValue: data['title'] as String? ?? '',
            decoration: InputDecoration(
              hintText: UITextConstants.articleTitlePlaceholder,
              hintStyle: TextStyle(
                color: SettingsSemanticConstants.createInputHintColor(isDark),
                fontSize: SettingsSemanticConstants.createInputTitleFontSize,
              ),
              border: InputBorder.none,
              contentPadding: EdgeInsets.zero,
            ),
            style: TextStyle(
              color: fgColor,
              fontSize: SettingsSemanticConstants.createInputTitleFontSize,
              fontWeight: FontWeight.bold,
            ),
            onChanged: (v) => setState(() {
              _currentData = Map.from(_currentData);
              (_currentData['article'] as Map<String, dynamic>)['title'] = v;
            }),
          ),
          Padding(
            padding: EdgeInsets.only(top: 8),
            child: TextFormField(
              initialValue: data['content'] as String? ?? '',
              decoration: InputDecoration(
                hintText: UITextConstants.createArticleBodyHint,
                hintStyle: TextStyle(
                  color: SettingsSemanticConstants.createInputHintColor(isDark),
                  fontSize:
                      SettingsSemanticConstants.createInputArticleBodyFontSize,
                ),
                border: InputBorder.none,
                contentPadding: EdgeInsets.zero,
              ),
              style: TextStyle(
                color: fgColor,
                fontSize:
                    SettingsSemanticConstants.createInputArticleBodyFontSize,
              ),
              maxLines: 8,
              onChanged: (v) => setState(() {
                _currentData = Map.from(_currentData);
                (_currentData['article'] as Map<String, dynamic>)['content'] =
                    v;
              }),
            ),
          ),
        ],
      ),
      _buildPublishSettingsSection(
        tabKey: 'article',
        fgColor: fgColor,
        fgSecondary: fgSecondary,
        isDark: isDark,
      ),
    ];
  }

  Widget _buildExitConfirm(bool isDark, Color fgColor, Color fgSecondary) {
    return GestureDetector(
      onTap: () => setState(() => _showExitConfirm = false),
      behavior: HitTestBehavior.opaque,
      child: Material(
        color: Colors.black54,
        child: Center(
          child: GestureDetector(
            onTap: () {},
            child: Container(
              margin: EdgeInsets.all(AppSpacing.interGroupXl),
              padding: EdgeInsets.all(AppSpacing.interGroupLg),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.backgroundPrimary,
                ),
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Stack(
                    alignment: Alignment.center,
                    children: [
                      Text(
                        UITextConstants.saveDraftConfirm,
                        style: TextStyle(
                          fontSize: AppTypography.xl,
                          fontWeight: FontWeight.w600,
                          color: fgColor,
                        ),
                      ),
                      Positioned(
                        right: 0,
                        top: 0,
                        child: IconButton(
                          icon: Icon(
                            Icons.close,
                            color: fgSecondary,
                            size: AppSpacing.iconMedium,
                          ),
                          onPressed: () =>
                              setState(() => _showExitConfirm = false),
                          style: IconButton.styleFrom(
                            minimumSize: Size.square(
                              AppSpacing.iconButtonMinSizeSm,
                            ),
                            padding: EdgeInsets.zero,
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.interGroupXs),
                  Text(
                    UITextConstants.saveDraftHint,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: fgSecondary,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: AppSpacing.interGroupLg),
                  Row(
                    children: [
                      Expanded(
                        child: TextButton(
                          onPressed: _handleDiscardAndExit,
                          style: TextButton.styleFrom(
                            foregroundColor: fgSecondary,
                          ),
                          child: Text(UITextConstants.discardAndExit),
                        ),
                      ),
                      SizedBox(width: AppSpacing.interGroupSm),
                      Expanded(
                        child: FilledButton(
                          onPressed: _handleSaveAndExit,
                          style: FilledButton.styleFrom(
                            backgroundColor: AppColors.primaryColor,
                            foregroundColor: Colors.white,
                          ),
                          child: Text(UITextConstants.saveAndExit),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDraftsList(bool isDark, Color fgColor, Color fgSecondary) {
    final sorted = List<Map<String, dynamic>>.from(
      _savedDrafts,
    )..sort((a, b) => (b['updatedAt'] as int).compareTo(a['updatedAt'] as int));
    return Material(
      color: Colors.black54,
      child: Center(
        child: Container(
          margin: EdgeInsets.all(AppSpacing.interGroupLg),
          constraints: BoxConstraints(maxWidth: 400, maxHeight: 400),
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.backgroundPrimary,
            ),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: EdgeInsets.all(AppSpacing.containerMd),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '${UITextConstants.draftCount} (${_savedDrafts.length})',
                      style: TextStyle(
                        fontSize: AppTypography.xl,
                        fontWeight: FontWeight.bold,
                        color: fgColor,
                      ),
                    ),
                    IconButton(
                      onPressed: () => setState(() => _showDraftsList = false),
                      icon: Icon(Icons.close, color: fgSecondary),
                    ),
                  ],
                ),
              ),
              Flexible(
                child: sorted.isEmpty
                    ? Padding(
                        padding: EdgeInsets.all(AppSpacing.interGroupXl),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.inventory_2_outlined,
                              size: AppSpacing.iconLarge,
                              color: fgSecondary.withValues(alpha: 0.5),
                            ),
                            SizedBox(height: AppSpacing.interGroupXs),
                            Text(
                              UITextConstants.noDraft,
                              style: TextStyle(color: fgSecondary),
                            ),
                          ],
                        ),
                      )
                    : ListView.builder(
                        shrinkWrap: true,
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerMd,
                        ),
                        itemCount: sorted.length,
                        itemBuilder: (context, i) {
                          final d = sorted[i];
                          final type = d['type'] as String? ?? 'moment';
                          final title = type == 'moment'
                              ? UITextConstants.draftMoment
                              : type == 'photo'
                              ? UITextConstants.draftPhoto
                              : type == 'video'
                              ? UITextConstants.draftVideo
                              : UITextConstants.draftArticle;
                          final data = d['data'] as Map<String, dynamic>? ?? {};
                          final desc =
                              (data['content'] ?? data['title'] ?? '')
                                  as String;
                          final date = DateTime.fromMillisecondsSinceEpoch(
                            d['updatedAt'] as int,
                          );
                          final dateStr =
                              '${date.month}/${date.day} ${date.hour}:${date.minute.toString().padLeft(2, '0')}';
                          return ListTile(
                            title: Text(
                              title,
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: Text(
                              desc.isEmpty ? UITextConstants.unlabeled : desc,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: fgSecondary,
                              ),
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  dateStr,
                                  style: TextStyle(
                                    fontSize: AppTypography.xs,
                                    color: fgSecondary,
                                  ),
                                ),
                                IconButton(
                                  icon: Icon(
                                    Icons.delete_outline,
                                    size: AppSpacing.iconMedium,
                                    color: fgSecondary,
                                  ),
                                  onPressed: () =>
                                      _handleDeleteDraft(d['id'] as String),
                                ),
                              ],
                            ),
                            onTap: () => _handleRestoreDraft(d),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DashedBorderPainter extends CustomPainter {
  _DashedBorderPainter({
    required this.color,
    required this.strokeWidth,
    required this.dashLength,
    required this.dashGap,
    required this.radius,
  });

  final Color color;
  final double strokeWidth;
  final double dashLength;
  final double dashGap;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(radius));
    final path = Path()..addRRect(rrect);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..color = color;

    for (final metric in path.computeMetrics()) {
      double distance = 0;
      while (distance < metric.length) {
        final len = math.min(dashLength, metric.length - distance);
        canvas.drawPath(metric.extractPath(distance, distance + len), paint);
        distance += dashLength + dashGap;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _DashedBorderPainter oldDelegate) {
    return oldDelegate.color != color ||
        oldDelegate.strokeWidth != strokeWidth ||
        oldDelegate.dashLength != dashLength ||
        oldDelegate.dashGap != dashGap ||
        oldDelegate.radius != radius;
  }
}
