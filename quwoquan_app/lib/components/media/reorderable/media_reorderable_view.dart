import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 统一的媒体拖拽重排视图（网格 / 横条两布局共用一套交互真相源）。
///
/// 设计目标（对齐用户「图片拖拽重排」诉求 + `.cursor/rules/13-coding-discipline` R24/R25）：
/// - 长按起拖 + 兄弟实时让位（[AnimatedPositioned] 前移/后移）+ 松手提交 + haptics；
/// - 网格（响应式 tile + 末尾「添加」占位）与横条（横向滚动）两种布局只此一处实现，
///   三个调用点（创作页网格 / 选择器已选条 / 图片编辑器缩略图条）共用，杜绝多套拖拽分叉；
/// - 几何只有一个真相源：[_slotOffset] 计算槽位坐标，拖拽中其余 tile 的展示槽位由
///   [_displayedSlotForItem] 统一推导；拖拽块跟随手指，松手时按最近槽位提交一次 [onReorder]。
///
/// 坐标系：组件用一个 [Stack] 承载全部 tile，所有几何运算都在 Stack 本地坐标完成。
/// 横条模式自带横向滚动与边缘自动滚动；网格模式不自滚（由外层页面滚动），
/// 其竖向边缘自动滚动通过 [onDragGlobalPositionChanged] 交回宿主页面处理（复用其既有逻辑）。
///
/// [onReorder] 采用 Flutter 标准约定：`newIndex` 为「原列表坐标系」中的插入位，范围 `0..itemCount`。
class MediaReorderableView extends StatefulWidget {
  const MediaReorderableView({
    super.key,
    required this.itemCount,
    required this.itemBuilder,
    required this.itemSize,
    required this.onReorder,
    this.layout = MediaReorderableLayout.grid,
    this.crossAxisCount = 1,
    this.spacing = 8,
    this.runSpacing = 8,
    this.trailing,
    this.enabled = true,
    this.onDragGlobalPositionChanged,
    this.onDragStart,
    this.onDragEnd,
    this.dragScale = 1.06,
    this.padding = EdgeInsets.zero,
    this.controller,
  }) : assert(itemCount >= 0),
       assert(crossAxisCount >= 1);

  /// 可重排 tile 数量（不含 [trailing]）。
  final int itemCount;

  /// tile 内容构造器。`isDragging` 为 true 表示该 tile 正被拖动（宿主可据此弱化静态副本）。
  final Widget Function(BuildContext context, int index, bool isDragging)
  itemBuilder;

  /// 每个 tile 的固定尺寸（宿主按布局约束算好后传入，保证槽位几何确定）。
  final Size itemSize;

  /// 提交重排。`newIndex` 为 Flutter 标准插入位（`0..itemCount`）。
  final void Function(int oldIndex, int newIndex) onReorder;

  final MediaReorderableLayout layout;

  /// 网格列数（横条模式忽略）。
  final int crossAxisCount;

  /// 主轴方向相邻 tile 间距。
  final double spacing;

  /// 网格换行方向（交叉轴）行间距。
  final double runSpacing;

  /// 末尾固定占位（如创作页「添加图片」格）。不参与拖动，但可作为「移到末尾」的落点区域。
  final Widget? trailing;

  final bool enabled;

  /// 拖拽过程中持续回传指针全局坐标，供宿主做竖向边缘自动滚动（网格模式）。
  final ValueChanged<Offset>? onDragGlobalPositionChanged;

  final ValueChanged<int>? onDragStart;
  final VoidCallback? onDragEnd;

  /// 拖拽块放大倍率。
  final double dragScale;

  final EdgeInsets padding;

  /// 横条模式可选的外部滚动控制器（如编辑器需「切页自动滚动到选中缩略图」）。
  /// 不传则组件内部自建并负责释放；外部传入则由外部负责释放。
  final ScrollController? controller;

  @override
  State<MediaReorderableView> createState() => _MediaReorderableViewState();
}

enum MediaReorderableLayout { grid, strip }

class _MediaReorderableViewState extends State<MediaReorderableView> {
  final GlobalKey _stackKey = GlobalKey();
  ScrollController? _ownedStripController;

  ScrollController? get _stripController =>
      widget.controller ?? _ownedStripController;

  /// 正在拖动的原始索引；null 表示未拖动。
  int? _dragIndex;

  /// 拖动块当前在「物品序列」中的落点（0..itemCount-1）。
  int _restIndex = 0;

  /// 指针在 Stack 本地坐标。
  Offset _pointerLocal = Offset.zero;

  /// 起拖时指针相对 tile 左上角的偏移，使拖拽块自然贴合手指。
  Offset _grabOffset = Offset.zero;

  Timer? _edgeScrollTimer;
  double _edgeScrollVelocity = 0;

  bool get _isStrip => widget.layout == MediaReorderableLayout.strip;

  @override
  void initState() {
    super.initState();
    if (_isStrip && widget.controller == null) {
      _ownedStripController = ScrollController();
    }
  }

  @override
  void dispose() {
    _edgeScrollTimer?.cancel();
    _ownedStripController?.dispose();
    super.dispose();
  }

  double get _tileW => widget.itemSize.width;
  double get _tileH => widget.itemSize.height;

  int get _slotCount => widget.itemCount + (widget.trailing != null ? 1 : 0);

  int get _columns =>
      _isStrip ? _slotCount.clamp(1, 1 << 30) : widget.crossAxisCount;

  int get _rows => _isStrip ? 1 : ((_slotCount + _columns - 1) ~/ _columns);

  Offset _slotOffset(int slotIndex) {
    if (_isStrip) {
      return Offset(slotIndex * (_tileW + widget.spacing), 0);
    }
    final col = slotIndex % _columns;
    final row = slotIndex ~/ _columns;
    return Offset(
      col * (_tileW + widget.spacing),
      row * (_tileH + widget.runSpacing),
    );
  }

  Size get _contentSize {
    if (_slotCount == 0) {
      return Size(widget.padding.horizontal, _tileH + widget.padding.vertical);
    }
    if (_isStrip) {
      final w = _slotCount * _tileW + (_slotCount - 1) * widget.spacing;
      return Size(
        w + widget.padding.horizontal,
        _tileH + widget.padding.vertical,
      );
    }
    final w = _columns * _tileW + (_columns - 1) * widget.spacing;
    final h = _rows * _tileH + (_rows - 1) * widget.runSpacing;
    return Size(w + widget.padding.horizontal, h + widget.padding.vertical);
  }

  /// 拖动中：item j（j != dragIndex）应展示在哪个槽位。
  int _displayedSlotForItem(int j) {
    final d = _dragIndex;
    if (d == null) return j;
    // 构造移除拖拽项后、在 _restIndex 处回插的序列，item j 的位置即其展示槽位。
    // 等价快速推导：
    if (j == d) return _restIndex; // 不会用到（拖拽项单独渲染）
    final lo = d < _restIndex ? d : _restIndex;
    final hi = d < _restIndex ? _restIndex : d;
    if (j < lo || j > hi) return j;
    return d < _restIndex ? j - 1 : j + 1;
  }

  /// 指针落在哪个「物品槽位」（0..itemCount-1）。
  int _restIndexForPointer(Offset local) {
    final p = Offset(
      local.dx - widget.padding.left,
      local.dy - widget.padding.top,
    );
    int best = 0;
    double bestDist = double.infinity;
    for (var i = 0; i < widget.itemCount; i++) {
      final c = _slotOffset(i) + Offset(_tileW / 2, _tileH / 2);
      final d = (c - p).distanceSquared;
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    }
    // 指针越过末尾占位（或最后一个 tile 之后）时，落点固定为末尾。
    if (widget.trailing != null) {
      final trailingOffset = _slotOffset(widget.itemCount);
      final beyond = _isStrip
          ? p.dx > trailingOffset.dx
          : (p.dy > trailingOffset.dy + _tileH / 2 ||
                (p.dy > trailingOffset.dy &&
                    p.dx > trailingOffset.dx + _tileW / 2));
      if (beyond && widget.itemCount > 0) {
        best = widget.itemCount - 1;
      }
    }
    return best.clamp(0, widget.itemCount > 0 ? widget.itemCount - 1 : 0);
  }

  Offset _toLocal(Offset global) {
    final box = _stackKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return global;
    return box.globalToLocal(global);
  }

  void _startDrag(int index, Offset globalPosition) {
    if (!widget.enabled || widget.itemCount <= 1) return;
    final local = _toLocal(globalPosition);
    HapticFeedback.mediumImpact();
    setState(() {
      _dragIndex = index;
      _restIndex = index;
      _pointerLocal = local;
      _grabOffset = Offset(
        local.dx - (widget.padding.left + _slotOffset(index).dx),
        local.dy - (widget.padding.top + _slotOffset(index).dy),
      );
    });
    widget.onDragStart?.call(index);
  }

  void _updateDrag(Offset globalPosition) {
    if (_dragIndex == null) return;
    final local = _toLocal(globalPosition);
    final nextRest = _restIndexForPointer(local);
    widget.onDragGlobalPositionChanged?.call(globalPosition);
    _maybeEdgeScroll(globalPosition);
    if (nextRest != _restIndex) {
      HapticFeedback.selectionClick();
    }
    setState(() {
      _pointerLocal = local;
      _restIndex = nextRest;
    });
  }

  void _endDrag() {
    final d = _dragIndex;
    _stopEdgeScroll();
    if (d == null) return;
    final rest = _restIndex;
    HapticFeedback.selectionClick();
    setState(() {
      _dragIndex = null;
    });
    widget.onDragEnd?.call();
    if (rest != d) {
      final newIndex = rest >= d ? rest + 1 : rest;
      widget.onReorder(d, newIndex);
    }
  }

  void _cancelDrag() {
    _stopEdgeScroll();
    if (_dragIndex == null) return;
    setState(() {
      _dragIndex = null;
    });
    widget.onDragEnd?.call();
  }

  // 横条模式：指针接近左右边缘时自动滚动内部控制器。
  void _maybeEdgeScroll(Offset globalPosition) {
    if (!_isStrip) return;
    final controller = _stripController;
    final box = _stackKey.currentContext?.findRenderObject() as RenderBox?;
    if (controller == null || box == null || !box.hasSize) return;
    // Stack 在横向滚动视图内，用其 viewport（视口）边界判断更稳妥：取组件可见区。
    final viewport = controller.position;
    final localX = box.globalToLocal(globalPosition).dx;
    const edge = 48.0;
    const maxSpeed = 14.0;
    double velocity = 0;
    final viewWidth = viewport.viewportDimension;
    // localX 是内容坐标，需转换为视口坐标：内容 x - 滚动偏移。
    final viewX = localX - viewport.pixels;
    if (viewX < edge && viewport.pixels > viewport.minScrollExtent) {
      velocity = -maxSpeed * (1 - (viewX / edge)).clamp(0.0, 1.0);
    } else if (viewX > viewWidth - edge &&
        viewport.pixels < viewport.maxScrollExtent) {
      velocity = maxSpeed * (1 - ((viewWidth - viewX) / edge)).clamp(0.0, 1.0);
    }
    _edgeScrollVelocity = velocity;
    if (velocity == 0) {
      _stopEdgeScroll();
    } else {
      _edgeScrollTimer ??= Timer.periodic(
        const Duration(milliseconds: 16),
        (_) => _tickEdgeScroll(),
      );
    }
  }

  void _tickEdgeScroll() {
    final controller = _stripController;
    if (controller == null || !controller.hasClients) return;
    final next = (controller.offset + _edgeScrollVelocity).clamp(
      controller.position.minScrollExtent,
      controller.position.maxScrollExtent,
    );
    controller.jumpTo(next);
  }

  void _stopEdgeScroll() {
    _edgeScrollTimer?.cancel();
    _edgeScrollTimer = null;
    _edgeScrollVelocity = 0;
  }

  @override
  Widget build(BuildContext context) {
    if (_isStrip) {
      return LayoutBuilder(
        builder: (context, constraints) {
          final content = _buildStack();
          final stripContent = constraints.maxWidth.isFinite
              ? ConstrainedBox(
                  constraints: BoxConstraints(minWidth: constraints.maxWidth),
                  child: content,
                )
              : content;
          return SizedBox(
            height: _contentSize.height,
            child: SingleChildScrollView(
              controller: _stripController,
              scrollDirection: Axis.horizontal,
              physics: _dragIndex != null
                  ? const NeverScrollableScrollPhysics()
                  : null,
              child: stripContent,
            ),
          );
        },
      );
    }
    return _buildStack();
  }

  Widget _buildStack() {
    final size = _contentSize;
    final children = <Widget>[];

    for (var i = 0; i < widget.itemCount; i++) {
      final isDragging = _dragIndex == i;
      // 关键：拖拽项仍在原占位渲染（保持同一 GestureDetector 存活，避免长按手势被
      // setState 重建销毁而中途取消），只是透明；可见的跟随块由下方 IgnorePointer 单独置顶。
      final slotIndex = isDragging ? _restIndex : _displayedSlotForItem(i);
      final slot = _slotOffset(slotIndex);
      final tile = _wrapGesture(i, widget.itemBuilder(context, i, isDragging));
      children.add(
        AnimatedPositioned(
          key: ValueKey<int>(i),
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOutCubic,
          left: widget.padding.left + slot.dx,
          top: widget.padding.top + slot.dy,
          width: _tileW,
          height: _tileH,
          child: Opacity(opacity: isDragging ? 0.0 : 1.0, child: tile),
        ),
      );
    }

    if (widget.trailing != null) {
      final slot = _slotOffset(widget.itemCount);
      children.add(
        Positioned(
          left: widget.padding.left + slot.dx,
          top: widget.padding.top + slot.dy,
          width: _tileW,
          height: _tileH,
          child: widget.trailing!,
        ),
      );
    }

    // 拖拽块置顶，跟随手指。
    final d = _dragIndex;
    if (d != null) {
      children.add(
        Positioned(
          left: _pointerLocal.dx - _grabOffset.dx,
          top: _pointerLocal.dy - _grabOffset.dy,
          width: _tileW,
          height: _tileH,
          child: IgnorePointer(
            child: Transform.scale(
              scale: widget.dragScale,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  boxShadow: <BoxShadow>[
                    BoxShadow(
                      color: AppColors.black.withValues(alpha: 0.28),
                      blurRadius: 18,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: widget.itemBuilder(context, d, true),
              ),
            ),
          ),
        ),
      );
    }

    return SizedBox(
      key: _stackKey,
      width: size.width,
      height: size.height,
      child: Stack(clipBehavior: Clip.none, children: children),
    );
  }

  Widget _wrapGesture(int index, Widget child) {
    if (!widget.enabled || widget.itemCount <= 1) return child;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onLongPressStart: (d) => _startDrag(index, d.globalPosition),
      onLongPressMoveUpdate: (d) => _updateDrag(d.globalPosition),
      onLongPressEnd: (_) => _endDrag(),
      onLongPressCancel: _cancelDrag,
      child: child,
    );
  }
}
