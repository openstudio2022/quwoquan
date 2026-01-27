import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';
export 'comment_viewer_modal.dart' show CommentViewer;



/// 评论输入组件
class CommentInput extends StatefulWidget {
  final CommentConfig config;
  final CommentModel? replyTo;
  final Function(String)? onSubmit;
  final VoidCallback? onCancelReply;
  final String? hintText;
  final bool enabled;

  const CommentInput({
    super.key,
    required this.config,
    this.replyTo,
    this.onSubmit,
    this.onCancelReply,
    this.hintText,
    this.enabled = true,
  });

  @override
  State<CommentInput> createState() => _CommentInputState();
}

class _CommentInputState extends State<CommentInput> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _isComposing = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onTextChanged);
  }

  @override
  void dispose() {
    _controller.removeListener(_onTextChanged);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    final isComposing = _controller.text.trim().isNotEmpty;
    if (_isComposing != isComposing) {
      setState(() {
        _isComposing = isComposing;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    return Container(
      padding: CommentResponsive.getModalPadding(context),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: 1,
          ),
        ),
      ),
      child: Column(
        children: [
          // 回复提示
          if (widget.replyTo != null) _buildReplyIndicator(context, isDark),
          
          // 输入区域
          _buildInputArea(context, isDark),
        ],
      ),
    );
  }

  /// 构建回复提示
  Widget _buildReplyIndicator(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: CommentResponsive.getContainerSpacing(context, SpacingSize.sm),
        vertical: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs),
      ),
      margin: EdgeInsets.only(
        bottom: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm),
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: AppColors.primaryColor.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Icon(
            Icons.reply,
            size: CommentResponsive.getCommentItemIconSize(context),
            color: AppColors.primaryColor,
          ),
          
              SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          Expanded(
            child: Text(
              '${"回复"} @${widget.replyTo!.username}',
              style: TextStyle(
                fontSize: CommentResponsive.getFontSize(context, 12.0),
                color: AppColors.primaryColor,
              ),
            ),
          ),
          
          GestureDetector(
            onTap: widget.onCancelReply,
            child: Icon(
              Icons.close,
              size: CommentResponsive.getCommentItemIconSize(context),
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
            ),
          ),
        ],
      ),
    );
  }

  /// 构建输入区域
  Widget _buildInputArea(BuildContext context, bool isDark) {
    return Row(
      children: [
        // 头像
        CircleAvatar(
          radius: CommentResponsive.getAvatarSize(context) / 2,
          backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
          child: Icon(
            Icons.person,
            size: CommentResponsive.getAvatarSize(context) / 2,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
          ),
        ),
        
        SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm)),
        
        // 输入框
        Expanded(
          child: Material(
            color: Colors.transparent,
            child: Container(
              height: CommentResponsive.getInputHeight(context),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: _focusNode.hasFocus 
                    ? AppColors.primaryColor 
                    : AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
                  width: _focusNode.hasFocus ? 2 : 1,
                ),
              ),
              child: TextField(
              controller: _controller,
              focusNode: _focusNode,
              enabled: widget.enabled && widget.config.canUserComment,
              maxLines: null,
              textInputAction: TextInputAction.send,
              onSubmitted: _isComposing ? _onSubmit : null,
              decoration: InputDecoration(
                hintText: widget.hintText ?? _getHintText(),
                hintStyle: TextStyle(
                  fontSize: CommentResponsive.getFontSize(context, 14.0),
                  color: isDark 
                    ? AppColors.dark.foregroundTertiary 
                    : AppColors.light.foregroundTertiary,
                ),
                border: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(
                  horizontal: CommentResponsive.getContainerSpacing(context, SpacingSize.md),
                  vertical: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm),
                ),
              ),
              style: TextStyle(
                fontSize: CommentResponsive.getFontSize(context, 14.0),
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
              ),
            ),
          ),
        ),
        
        SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm)),
        
        // 发送按钮
        _buildSendButton(context, isDark),
      ],
    );
  }

  /// 构建发送按钮
  Widget _buildSendButton(BuildContext context, bool isDark) {
    final canSend = _isComposing && 
                   widget.enabled && 
                   widget.config.canUserComment;
    
    return GestureDetector(
      onTap: canSend ? _onSubmit : null,
      child: Container(
        width: CommentResponsive.getCommentItemSize(context),
        height: CommentResponsive.getCommentItemSize(context),
        decoration: BoxDecoration(
          color: canSend 
            ? AppColors.primaryColor 
            : AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
          borderRadius: BorderRadius.circular(CommentResponsive.getCommentItemSize(context) / 2),
        ),
        child: Icon(
          Icons.send,
          size: CommentResponsive.getCommentItemIconSize(context),
          color: canSend 
            ? Colors.white 
            : AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
        ),
      ),
    );
  }

  /// 获取提示文本
  String _getHintText() {
    if (!widget.config.canUserComment) {
      return widget.config.isUserLoggedIn 
        ? UITextConstants.commentClosed 
        : UITextConstants.needLogin;
    }
    
    if (widget.replyTo != null) {
      return CommentHierarchyManager.getReplyPlaceholder(widget.replyTo!);
    }
    
    return UITextConstants.commentPlaceholder;
  }

  /// 提交评论
  void _onSubmit([String? text]) {
    final content = (text ?? _controller.text).trim();
    
    if (content.isEmpty) {
      return;
    }
    
    // 检查内容长度
    if (content.length > 1000) {
      _showError(UITextConstants.commentTooLong);
      return;
    }
    
    widget.onSubmit?.call(content);
    _controller.clear();
    
    // 取消回复状态
    if (widget.replyTo != null) {
      widget.onCancelReply?.call();
    }
  }

  /// 显示错误信息
  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: AppColors.error,
      ),
    );
  }

  /// 清空输入
  void clear() {
    _controller.clear();
  }

  /// 设置焦点
  void focus() {
    _focusNode.requestFocus();
  }

  /// 设置回复目标
  void setReplyTo(CommentModel? comment) {
    // 这个方法需要在父组件中调用，因为replyTo是final的
    // 这里只是提供接口，实际实现需要在父组件中重新构建widget
  }
}

/// 评论输入工具类
class CommentInputUtils {
  /// 验证评论内容
  static String? validateComment(String content) {
    if (content.trim().isEmpty) {
      return UITextConstants.commentEmpty;
    }
    
    if (content.length > 1000) {
      return UITextConstants.commentTooLong;
    }
    
    return null;
  }

  /// 格式化评论内容
  static String formatComment(String content) {
    return content.trim();
  }

  /// 获取评论字数统计
  static int getCommentLength(String content) {
    return content.trim().length;
  }

  /// 检查是否可以发送
  static bool canSend(String content, CommentConfig config) {
    return content.trim().isNotEmpty && 
           config.canUserComment &&
           content.trim().length <= 1000;
  }
}
