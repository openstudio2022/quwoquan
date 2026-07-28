import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_image_album_scanner.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_picker_services.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_thumbnail_image_provider.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/app_top_anchored_dropdown.dart';

/// 桌面（本机文件系统）图片选择器。
///
/// 路由判据是能力位而非平台名：仅当 `mediaLibrary == false && hasLocalFileSystem`
/// （桌面 profile）时由创作流进入此页（见 `create_page._openMediaPicker`）。
/// 与移动端 `CreateMediaPickerPage` 形成对照——桌面无系统相册，改为「选目录 -> 递归扫描
/// 含图子目录 -> 聚合相册」。多选、拖拽重排、相册下拉全部复用统一组件，杜绝第二套交互。
///
/// 所有外部能力（文件枚举 / 目录选择 / 上次目录记忆）经 Provider 注入，便于 widget 测试
/// 用假实现驱动完整链路；缺能力位时结构化降级为空态，不崩溃。
class DesktopImagePickerPage extends ConsumerStatefulWidget {
  const DesktopImagePickerPage({
    super.key,
    required this.maxSelection,
    this.scanner = const DesktopImageAlbumScanner(),
  });

  final int maxSelection;
  final DesktopImageAlbumScanner scanner;

  @override
  ConsumerState<DesktopImagePickerPage> createState() =>
      _DesktopImagePickerPageState();
}

class _DesktopImagePickerPageState
    extends ConsumerState<DesktopImagePickerPage> {
  final GlobalKey _topBarKey = GlobalKey();

  List<DesktopImageAlbum> _albums = const <DesktopImageAlbum>[];
  DesktopImageAlbum? _selectedAlbum;
  final List<String> _selectedPaths = <String>[];
  String? _currentDirectory;
  bool _bootstrapping = true;
  bool _scanning = false;

  bool get _isDark =>
      CupertinoTheme.brightnessOf(context) == Brightness.dark;

  @override
  void initState() {
    super.initState();
    unawaited(_bootstrap());
  }

  Future<void> _bootstrap() async {
    final gateway = ref.read(fileStorageGatewayProvider);
    if (!gateway.isSupported) {
      if (!mounted) return;
      setState(() => _bootstrapping = false);
      return;
    }
    final memory = ref.read(desktopPickerDirectoryMemoryProvider);
    final last = await memory.lastDirectory();
    if (!mounted) return;
    if (last != null) {
      await _scanDirectory(last);
    }
    if (!mounted) return;
    setState(() => _bootstrapping = false);
  }

  Future<void> _pickDirectory() async {
    final picker = ref.read(desktopDirectoryPickerProvider);
    final chosen = await picker.pickDirectory(
      initialDirectory: _currentDirectory,
    );
    if (chosen == null || chosen.isEmpty) {
      return;
    }
    await ref
        .read(desktopPickerDirectoryMemoryProvider)
        .rememberDirectory(chosen);
    await _scanDirectory(chosen);
  }

  Future<void> _scanDirectory(String path) async {
    final gateway = ref.read(fileStorageGatewayProvider);
    if (!mounted) return;
    setState(() {
      _scanning = true;
      _currentDirectory = path;
    });
    final albums = await widget.scanner.scan(gateway, path);
    if (!mounted) return;
    setState(() {
      _albums = albums;
      _selectedAlbum = albums.isNotEmpty ? albums.first : null;
      _scanning = false;
    });
  }

  void _toggleSelection(String path) {
    setState(() {
      if (_selectedPaths.contains(path)) {
        _selectedPaths.remove(path);
        return;
      }
      if (_selectedPaths.length >= widget.maxSelection) {
        HapticFeedback.selectionClick();
        AppToast.show(context, MediaText.mediaPickerOverLimit);
        return;
      }
      _selectedPaths.add(path);
    });
  }

  void _reorderSelected(int oldIndex, int newIndex) {
    setState(() {
      final to = oldIndex < newIndex ? newIndex - 1 : newIndex;
      final moved = _selectedPaths.removeAt(oldIndex);
      _selectedPaths.insert(to, moved);
    });
  }

  void _finish() {
    final items = _selectedPaths
        .map(
          (path) => CreateMediaItem(
            id: path,
            path: path,
            type: CreateMediaType.image,
            source: CreateMediaSource.album,
          ),
        )
        .toList(growable: false);
    Navigator.of(context).pop(CreateMediaPickerResult(items: items));
  }

  TextStyle _titleStyle() => TextStyle(
        fontSize: AppTypography.lg,
        fontWeight: AppTypography.semiBold,
        color: AppColorsFunctional.getColor(
          _isDark,
          ColorType.foregroundPrimary,
        ),
      );

  TextStyle _bodyStyle() => TextStyle(
        fontSize: AppTypography.base,
        color: AppColorsFunctional.getColor(
          _isDark,
          ColorType.foregroundPrimary,
        ),
      );

  TextStyle _subStyle() => TextStyle(
        fontSize: AppTypography.sm,
        color: AppColorsFunctional.getColor(
          _isDark,
          ColorType.foregroundSecondary,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final isDark = _isDark;
    return AppScaffold(
      backgroundColor: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundPrimary,
      ),
      navigationBar: AppNavigationBar(
        middle: Text(MediaText.mediaPickerPhotoTitle),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: () => Navigator.of(context).pop(),
        ),
        trailing: _currentDirectory == null
            ? null
            : CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: _scanning ? null : () => unawaited(_pickDirectory()),
                child: Text(MediaText.desktopPickerChangeFolder),
              ),
      ),
      child: SafeArea(child: _buildBody(isDark)),
    );
  }

  Widget _buildBody(bool isDark) {
    final gateway = ref.read(fileStorageGatewayProvider);
    if (!gateway.isSupported) {
      return _buildCenteredEmpty(
        icon: CupertinoIcons.device_desktop,
        title: MediaText.desktopPickerUnsupportedTitle,
        message: MediaText.desktopPickerUnsupportedHint,
      );
    }
    if (_bootstrapping || _scanning) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const CupertinoActivityIndicator(),
            SizedBox(height: AppSpacing.containerSm),
            Text(MediaText.desktopPickerScanning, style: _subStyle()),
          ],
        ),
      );
    }
    if (_currentDirectory == null) {
      return _buildEmptyChooseFolder();
    }
    final album = _selectedAlbum;
    final images = album?.imagePaths ?? const <String>[];
    return Column(
      children: <Widget>[
        _buildAlbumBar(isDark),
        Expanded(
          child: images.isEmpty
              ? _buildCenteredEmpty(
                  icon: CupertinoIcons.photo,
                  title: MediaText.desktopPickerNoImages,
                  message: '',
                )
              : _buildGrid(images, isDark),
        ),
        if (_selectedPaths.isNotEmpty) _buildSelectedStrip(isDark),
        _buildConfirmBar(),
      ],
    );
  }

  Widget _buildCenteredEmpty({
    required IconData icon,
    required String title,
    required String message,
  }) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            icon,
            size: AppSpacing.iconLarge,
            color: AppColorsFunctional.getColor(
              _isDark,
              ColorType.foregroundTertiary,
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Text(title, style: _titleStyle()),
          if (message.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(message, style: _subStyle(), textAlign: TextAlign.center),
          ],
        ],
      ),
    );
  }

  Widget _buildEmptyChooseFolder() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            CupertinoIcons.folder,
            size: AppSpacing.iconLarge,
            color: AppColorsFunctional.getColor(
              _isDark,
              ColorType.foregroundTertiary,
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Text(MediaText.desktopPickerEmptyTitle, style: _titleStyle()),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            MediaText.desktopPickerEmptyHint,
            style: _subStyle(),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: AppSpacing.containerLg),
          CupertinoButton.filled(
            key: TestKeys.desktopPickerChooseFolderButton,
            onPressed: () => unawaited(_pickDirectory()),
            child: Text(MediaText.desktopPickerChooseFolder),
          ),
        ],
      ),
    );
  }

  Widget _buildAlbumBar(bool isDark) {
    final album = _selectedAlbum;
    return Container(
      key: _topBarKey,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _albums.length <= 1
                  ? null
                  : () => unawaited(_openAlbumDropdown()),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Flexible(
                    child: Text(
                      album?.name ??
                          MediaText.mediaPickerAlbumSelectionTitle,
                      style: _titleStyle(),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (_albums.length > 1)
                    Icon(
                      CupertinoIcons.chevron_down,
                      size: AppSpacing.iconSmall,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                ],
              ),
            ),
          ),
          if (album != null) Text('${album.count}', style: _subStyle()),
        ],
      ),
    );
  }

  Future<void> _openAlbumDropdown() async {
    final renderBox =
        _topBarKey.currentContext?.findRenderObject() as RenderBox?;
    final anchorTop = renderBox == null
        ? AppSpacing.appChromeNavigationBarHeight
        : renderBox.localToGlobal(Offset.zero).dy + renderBox.size.height;
    final selected = await showAppTopAnchoredDropdown<DesktopImageAlbum>(
      context: context,
      anchorTop: anchorTop,
      scrimColor: AppColors.black.withValues(alpha: 0.4),
      barrierLabel: MediaText.mediaPickerAlbumSelectionTitle,
      builder: _buildAlbumDropdownPanel,
    );
    if (selected != null && mounted) {
      setState(() => _selectedAlbum = selected);
    }
  }

  Widget _buildAlbumDropdownPanel(BuildContext dropdownContext) {
    return Container(
      key: TestKeys.mediaPickerAlbumDropdownPanel,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          _isDark,
          ColorType.backgroundPrimary,
        ),
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(AppSpacing.borderRadius),
        ),
      ),
      child: ListView.builder(
        shrinkWrap: true,
        itemCount: _albums.length,
        itemBuilder: (context, index) {
          final album = _albums[index];
          return CupertinoListTile(
            title: Text(album.name, style: _bodyStyle()),
            trailing: Text('${album.count}', style: _subStyle()),
            onTap: () => Navigator.of(dropdownContext).pop(album),
          );
        },
      ),
    );
  }

  Widget _buildGrid(List<String> images, bool isDark) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount =
            constraints.maxWidth >= AppSpacing.webPageContentMaxWidth
                ? 5
                : (constraints.maxWidth >= AppSpacing.expandedBreakpoint
                    ? 4
                    : 3);
        final spacing = AppSpacing.intraGroupSm;
        final tileWidth = (constraints.maxWidth -
                spacing * 2 -
                spacing * (crossAxisCount - 1)) /
            crossAxisCount;
        return GridView.builder(
          key: TestKeys.desktopPickerGrid,
          padding: EdgeInsets.all(AppSpacing.intraGroupSm),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: crossAxisCount,
            crossAxisSpacing: AppSpacing.intraGroupSm,
            mainAxisSpacing: AppSpacing.intraGroupSm,
          ),
          itemCount: images.length,
          itemBuilder: (context, index) {
            final path = images[index];
            final selectedIndex = _selectedPaths.indexOf(path);
            return _buildGridTile(path, selectedIndex, isDark, tileWidth);
          },
        );
      },
    );
  }

  Widget _buildGridTile(
    String path,
    int selectedIndex,
    bool isDark,
    double tileWidth,
  ) {
    final selected = selectedIndex >= 0;
    final brand = AppColorsFunctional.getColor(isDark, ColorType.primary);
    return GestureDetector(
      key: ValueKey<String>('desktop-picker-tile-$path'),
      onTap: () => _toggleSelection(path),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            child: _thumb(path, isDark, displaySize: tileWidth),
          ),
          if (selected)
            Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(color: brand, width: AppSpacing.two),
              ),
            ),
          Positioned(
            top: AppSpacing.intraGroupXs,
            right: AppSpacing.intraGroupXs,
            child: Container(
              width: AppSpacing.iconMedium,
              height: AppSpacing.iconMedium,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: selected
                    ? brand
                    : AppColors.black.withValues(alpha: 0.35),
                border: Border.all(color: AppColors.white),
              ),
              alignment: Alignment.center,
              child: selected
                  ? Text(
                      '${selectedIndex + 1}',
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        fontWeight: AppTypography.semiBold,
                        color: AppColors.white,
                      ),
                    )
                  : null,
            ),
          ),
        ],
      ),
    );
  }

  /// 缩略图：按显示边长降采样解码（[DesktopThumbnailImage]），解码图归全局 imageCache
  /// LRU 治理；加载/失败统一降级为占位色块，到帧后淡入（渐进观感）。
  Widget _thumb(String path, bool isDark, {required double displaySize}) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final targetPx = (displaySize * dpr).round().clamp(1, 2048);
    final placeholder = Container(
      color: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundSecondary,
      ),
    );
    return Image(
      image: DesktopThumbnailImage(
        path,
        gateway: ref.read(fileStorageGatewayProvider),
        targetPx: targetPx,
      ),
      fit: BoxFit.cover,
      gaplessPlayback: true,
      errorBuilder: (context, error, stackTrace) => placeholder,
      frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
        if (wasSynchronouslyLoaded) {
          return child;
        }
        return AnimatedOpacity(
          opacity: frame == null ? 0 : 1,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          child: frame == null ? placeholder : child,
        );
      },
    );
  }

  Widget _buildSelectedStrip(bool isDark) {
    final thumbSize = AppSpacing.bottomNavHeight;
    return Container(
      height: AppSpacing.bottomNavHeight + AppSpacing.containerMd,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerXs,
      ),
      child: MediaReorderableView(
        layout: MediaReorderableLayout.strip,
        itemCount: _selectedPaths.length,
        spacing: AppSpacing.intraGroupSm,
        itemSize: Size(thumbSize, thumbSize),
        onReorder: _reorderSelected,
        itemBuilder: (context, index, isDragging) {
          final path = _selectedPaths[index];
          return _buildStripThumb(path, isDark);
        },
      ),
    );
  }

  Widget _buildStripThumb(String path, bool isDark) {
    final size = AppSpacing.bottomNavHeight;
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Container(
          width: size,
          height: size,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            border: Border.all(
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.borderSecondary,
              ),
            ),
          ),
          child: _thumb(path, isDark, displaySize: size),
        ),
        Positioned(
          right: -AppSpacing.intraGroupXs,
          top: -AppSpacing.intraGroupXs,
          child: GestureDetector(
            onTap: () => setState(() => _selectedPaths.remove(path)),
            child: Container(
              width: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
              height: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.black.withValues(alpha: 0.87),
              ),
              child: Icon(
                Icons.close,
                color: AppColors.white,
                size: AppSpacing.iconSmall,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildConfirmBar() {
    final count = _selectedPaths.length;
    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: SizedBox(
          width: double.infinity,
          child: CupertinoButton.filled(
            key: TestKeys.desktopPickerConfirmButton,
            onPressed: count == 0 ? null : _finish,
            child: Text(
              count == 0
                  ? MediaText.mediaPickerComplete
                  : '${MediaText.mediaPickerComplete} ($count)',
            ),
          ),
        ),
      ),
    );
  }
}
