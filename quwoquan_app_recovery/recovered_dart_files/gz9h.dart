import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_responsive.dart';
import 'comment_models.dart';

/// 评论弹窗配置（简化版）
class CommentModalConfig {
  /// 是否启用拖拽
  final bool enableDrag;
  /// 评论数量
  final int commentCount;
  
  const CommentModalConfig({
    this.enableDrag = true,
    this.commentCount = 0,
  });
}

/// 可拖拽的评论弹窗组件
class CommentModal extends StatefulWidget {
  final String title;
  final Widget child;
  final VoidCallback? onClose;
  final CommentConfig config;
  final CommentModalConfig modalConfig;

  const CommentModal({
    Key? key,
    required this.title,
    required this.child,
    this.onClose,
    required this.config,
    CommentModalConfig? modalConfig,
  }) : modalConfig = modalConfig ?? const CommentModalConfig(),
       super(key: key);

  @override
  State<CommentModal> createState() => _CommentModalState();

  /// 显示评论弹窗（使用 showModalBottomSheet 模式）
  static Future<void> show({
    required BuildContext context,
    required String title,
    required Widget child,
    required CommentConfig config,
    CommentModalConfig? modalConfig,
    VoidCallback? onClose,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black54,
      builder: (context) => CommentModal(
        title: title,
        child: child,
        config: config,
        modalConfig: modalConfig,
        onClose: onClose,
      ),
    );
  }
}

class _CommentModalState extends State<CommentModal>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _animation;
  
  double _currentHeight = 0.6; // 默认高度（60%屏幕高度）
  bool _isDragging = false;
  double _dragStartHeight = 0.0;
  double _dragStartY = 0.0;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _animation = Tween<double>(
      begin: 0.0,
      end: _currentHeight,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    ));
    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    // 计算实际高度（考虑底部安全区域）
    final actualHeight = screenHeight * _currentHeight;
    final minHeight = screenHeight * widget.config.minModalHeight;
    final maxHeight = screenHeight * widget.config.maxModalHeight;
    
    // 确保高度在允许范围内
    final clampedHeight = actualHeight.clamp(minHeight, maxHeight);

    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Container(
          height: clampedHeight + bottomPadding,
          decoration: BoxDecoration(
            color: isDark 
              ? AppColors.dark.backgroundPrimary 
              : AppColors.light.backgroundPrimary,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
            boxShadow: [
              BoxShadow(
                color: isDark 
                  ? Colors.black.withOpacity(0.3)
                  : Colors.black.withOpacity(0.1),
                blurRadius: 10,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: Column(
            children: [
              // 拖拽指示器和标题栏
              _buildHeader(context, isDark),
              
              // 内容区域
              Expanded(
                child: widget.child,
              ),
              
              // 底部安全区域
              if (bottomPadding > 0)
                Container(
                  height: bottomPadding,
                  color: isDark 
                    ? AppColors.dark.backgroundPrimary 
                    : AppColors.light.backgroundPrimary,
                ),
            ],
          ),
        );
      },
    );
  }

  /// 构建头部（拖拽指示器 + 标题栏）
  Widget _buildHeader(BuildContext context, bool isDark) {
    return Container(
      padding: CommentResponsive.getModalPadding(context),
      child: Column(
        children: [
          // 拖拽指示器
          if (widget.modalConfig.enableDrag) _buildDragHandle(context, isDark),
          
          // 标题栏
          _buildTitleBar(context, isDark),
        ],
      ),
    );
  }

  /// 构建拖拽指示器
  Widget _buildDragHandle(BuildContext context, bool isDark) {
    final handleWidth = CommentResponsive.getModalDragHandleWidth(context);
    final handleHeight = CommentResponsive.getModalDragHandleHeight(context);
    
    return GestureDetector(
      onPanStart: _onDragStart,
      onPanUpdate: _onDragUpdate,
      onPanEnd: _onDragEnd,
      child: Container(
        width: handleWidth,
        height: handleHeight,
        margin: EdgeInsets.only(
          bottom: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm),
        ),
        decoration: BoxDecoration(
          color: isDark 
            ? AppColors.dark.foregroundTertiary 
            : AppColors.light.foregroundTertiary,
          borderRadius: BorderRadius.circular(handleHeight / 2),
        ),
      ),
    );
  }

  /// 构建标题栏
  Widget _buildTitleBar(BuildContext context, bool isDark) {
    final titleFontSize = CommentResponsive.getModalTitleFontSize(context);
    
    return Row(
      children: [
        // 标题 - 居中显示评论数和标题
        Expanded(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                widget.title,
                style: TextStyle(
                  fontSize: titleFontSize,
                  fontWeight: FontWeight.w600,
                  color: isDark 
                    ? AppColors.dark.foregroundPrimary 
                    : AppColors.light.foregroundPrimary,
                ),
              ),
              if (widget.modalConfig.commentCount > 0) ...[
                SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
                Text(
                  '${widget.modalConfig.commentCount}',
                  style: TextStyle(
                    fontSize: titleFontSize,
                    fontWeight: FontWeight.w600,
                    color: isDark 
                      ? AppColors.dark.foregroundPrimary 
                      : AppColors.light.foregroundPrimary,
                  ),
                ),
              ],
            ],
          ),
        ),
        
        // 关闭按钮
        GestureDetector(
          onTap: () {
            _closeModal();
          },
          child: Container(
            padding: EdgeInsets.all(
              CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs),
            ),
            decoration: BoxDecoration(
              color: isDark 
                ? AppColors.dark.backgroundSecondary 
                : AppColors.light.backgroundSecondary,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.close,
              size: CommentResponsive.getCommentItemIconSize(context),
              color: isDark 
                ? AppColors.dark.foregroundSecondary 
                : AppColors.light.foregroundSecondary,
            ),
          ),
        ),
      ],
    );
  }

  /// 拖拽开始
  void _onDragStart(DragStartDetails details) {
    if (!widget.modalConfig.enableDrag) return;
    
    setState(() {
      _isDragging = true;
      _dragStartHeight = _currentHeight;
      _dragStartY = details.globalPosition.dy;
    });
  }

  /// 拖拽更新
  void _onDragUpdate(DragUpdateDetails details) {
    if (!widget.modalConfig.enableDrag || !_isDragging) return;
    
    final screenHeight = MediaQuery.of(context).size.height;
    final deltaY = _dragStartY - details.globalPosition.dy; // 向上拖拽为正
    final deltaHeight = deltaY / screenHeight;
    
    final newHeight = _dragStartHeight + deltaHeight;
    final minHeight = widget.config.minModalHeight;
    final maxHeight = widget.config.maxModalHeight;
    
    setState(() {
      _currentHeight = newHeight.clamp(minHeight, maxHeight);
    });
  }

  /// 拖拽结束
  void _onDragEnd(DragEndDetails details) {
    if (!widget.modalConfig.enableDrag || !_isDragging) return;
    
    setState(() {
      _isDragging = false;
    });
    
    // 根据拖拽方向和速度决定最终位置
    final velocity = details.velocity.pixelsPerSecond.dy;
    
    if (velocity.abs() > 500) {
      // 快速拖拽，根据方向决定位置
      if (velocity > 0) {
        // 向下拖拽，关闭弹窗
        _closeModal();
        return;
      } else {
        // 向上拖拽，最大化
        _animateToHeight(widget.config.maxModalHeight);
      }
    } else {
      // 慢速拖拽，根据当前位置决定最近的吸附点
      _snapToNearestHeight();
    }
  }

  /// 吸附到最近的高度
  void _snapToNearestHeight() {
    final minHeight = widget.config.minModalHeight;
    final maxHeight = widget.config.maxModalHeight;
    final midHeight = (minHeight + maxHeight) / 2;
    
    double targetHeight;
    if (_currentHeight < midHeight) {
      targetHeight = minHeight;
    } else {
      targetHeight = maxHeight;
    }
    
    _animateToHeight(targetHeight);
  }

  /// 动画到指定高度
  void _animateToHeight(double targetHeight) {
    setState(() {
      _currentHeight = targetHeight;
    });
    
    _animationController.reset();
    _animation = Tween<double>(
      begin: _currentHeight,
      end: _currentHeight,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    ));
    _animationController.forward();
  }

  /// 关闭弹窗（简化版 - 直接使用 pop）
  void _closeModal() {
    widget.onClose?.call();
    Navigator.of(context).pop();
  }
}

/// 评论弹窗工具类（简化版）
class CommentModalUtils {
  /// 创建评论弹窗配置
  static CommentModalConfig createConfig({
    bool enableDrag = true,
    int commentCount = 0,
  }) {
    return CommentModalConfig(
      enableDrag: enableDrag,
      commentCount: commentCount,
    );
  }
  /// 计算弹窗初始高度
  static double calculateInitialHeight(
    BuildContext context,
    CommentConfig config,
    int commentCount,
    int totalReplies,
  ) {
    final screenHeight = MediaQuery.of(context).size.height;
    final minHeight = screenHeight * config.minModalHeight;
    final maxHeight = screenHeight * config.maxModalHeight;
    
    // 根据内容估算高度
    final estimatedHeight = CommentResponsive.getModalHeight(
      context,
      CommentModalHeight.adaptive,
      commentCount,
      totalReplies,
    );
    
    // 确保在允许范围内
    return estimatedHeight.clamp(minHeight, maxHeight) / screenHeight;
  }

  /// 获取弹窗样式
  static BoxDecoration getModalDecoration(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    return BoxDecoration(
      color: isDark 
        ? AppColors.dark.backgroundPrimary 
        : AppColors.light.backgroundPrimary,
      borderRadius: const BorderRadius.only(
        topLeft: Radius.circular(20),
        topRight: Radius.circular(20),
      ),
      boxShadow: [
        BoxShadow(
          color: isDark 
            ? Colors.black.withOpacity(0.3)
            : Colors.black.withOpacity(0.1),
          blurRadius: 10,
          offset: const Offset(0, -2),
        ),
      ],
    );
  }

  /// 检查是否可以拖拽
  static bool canDrag(CommentConfig config) {
    return config.enableDragModal && 
           config.maxModalHeight > config.minModalHeight;
  }
}
