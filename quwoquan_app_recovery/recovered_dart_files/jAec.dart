import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';
import 'comment_responsive.dart';
import 'comment_modal.dart';
import 'comment_service_impl.dart';
import 'comment_list.dart';
import 'comment_input.dart';

/// 评论服务工具类
class CommentServiceUtils {
  /// 验证评论文本
  static String? validateCommentText(String content) {
    if (content.trim().isEmpty) {
      return '评论内容不能为空';
    }
    if (content.length > 1000) {
      return '评论内容不能超过1000个字符';
    }
    return null;
  }
}

/// 主评论查看器组件
class CommentViewer extends ConsumerStatefulWidget {
  final String postId;
  final List<CommentModel> initialComments;
  final CommentConfig config;
  final CommentDisplayMode displayMode;
  final CommentModalHeight modalHeight;
  final Function(String)? onCommentAdded;
  final Function(CommentModel)? onCommentLiked;
  final Function(String, String)? onReplyAdded;
  final Function(CommentModel)? onUserTapped;
  final VoidCallback? onLoadMore;
  final VoidCallback? onClose;

  const CommentViewer({
    super.key,
    required this.postId,
    required this.initialComments,
    required this.config,
    this.displayMode = CommentDisplayMode.modal,
    this.modalHeight = CommentModalHeight.adaptive,
    this.onCommentAdded,
    this.onCommentLiked,
    this.onReplyAdded,
    this.onUserTapped,
    this.onLoadMore,
    this.onClose,
  });

  @override
  ConsumerState<CommentViewer> createState() => _CommentViewerState();

  /// 显示评论弹窗
  static Future<void> showModal({
    required BuildContext context,
    required String postId,
    required List<CommentModel> initialComments,
    required CommentConfig config,
    CommentModalHeight modalHeight = CommentModalHeight.adaptive,
    Function(String)? onCommentAdded,
    Function(CommentModel)? onCommentLiked,
    Function(String, String)? onReplyAdded,
    Function(CommentModel)? onUserTapped,
    VoidCallback? onLoadMore,
    VoidCallback? onClose,
  }) {
    return CommentModal.show(
      context: context,
      title: UITextConstants.comments,
      config: config,
      modalConfig: CommentModalUtils.createConfig(
        enableDrag: CommentModalUtils.canDrag(config),
        commentCount: initialComments.length,
      ),
      onClose: onClose,
      child: CommentViewer(
        postId: postId,
        initialComments: initialComments,
        config: config,
        displayMode: CommentDisplayMode.modal,
        modalHeight: modalHeight,
        onCommentAdded: onCommentAdded,
        onCommentLiked: onCommentLiked,
        onReplyAdded: onReplyAdded,
        onUserTapped: onUserTapped,
        onLoadMore: onLoadMore,
        onClose: onClose,
      ),
    );
  }

  /// 显示全屏评论页面
  static Future<void> showFullScreen({
    required BuildContext context,
    required String postId,
    required List<CommentModel> initialComments,
    required CommentConfig config,
    Function(String)? onCommentAdded,
    Function(CommentModel)? onCommentLiked,
    Function(String, String)? onReplyAdded,
    Function(CommentModel)? onUserTapped,
    VoidCallback? onLoadMore,
    VoidCallback? onClose,
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => CommentViewer(
          postId: postId,
          initialComments: initialComments,
          config: config,
          displayMode: CommentDisplayMode.fullScreen,
          onCommentAdded: onCommentAdded,
          onCommentLiked: onCommentLiked,
          onReplyAdded: onReplyAdded,
          onUserTapped: onUserTapped,
          onLoadMore: onLoadMore,
          onClose: onClose,
        ),
      ),
    );
  }
}

class _CommentViewerState extends ConsumerState<CommentViewer> {
  final CommentListController _listController = CommentListController();
  CommentModel? _replyTo;
  final GlobalKey<State<CommentInput>> _inputKey = GlobalKey();
  bool _isLoading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _listController.setComments(widget.initialComments);
    
    // 如果没有初始评论，则从服务加载
    if (widget.initialComments.isEmpty) {
      _loadComments();
    }
  }

  /// 从评论服务加载评论数据
  Future<void> _loadComments() async {
    if (_isLoading) return;
    
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final commentService = ref.read(commentServiceProvider);
      final comments = await commentService.getPostComments(
        postId: widget.postId,
        page: 1,
        limit: 20,
      );
      
      if (mounted) {
        _listController.setComments(comments);
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    if (widget.displayMode == CommentDisplayMode.fullScreen) {
      return _buildFullScreenView(context, isDark);
    } else {
      return _buildModalView(context, isDark);
    }
  }

  /// 构建全屏视图
  Widget _buildFullScreenView(BuildContext context, bool isDark) {
    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      appBar: _buildAppBar(context, isDark),
      body: Column(
        children: [
          // 评论列表
          Expanded(
            child: _buildCommentList(context, isDark),
          ),
          
          // 输入框
          _buildCommentInput(context, isDark),
        ],
      ),
    );
  }

  /// 构建弹窗视图
  Widget _buildModalView(BuildContext context, bool isDark) {
    return Column(
      children: [
        // 评论列表
        Expanded(
          child: _buildCommentList(context, isDark),
        ),
        
        // 输入框
        _buildCommentInput(context, isDark),
      ],
    );
  }

  /// 构建应用栏
  PreferredSizeWidget _buildAppBar(BuildContext context, bool isDark) {
    final titleFontSize = CommentResponsive.getModalTitleFontSize(context);
    
    return AppBar(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      elevation: 0,
      leading: IconButton(
        icon: Icon(
          Icons.arrow_back,
          color: isDark 
            ? AppColors.dark.foregroundPrimary 
            : AppColors.light.foregroundPrimary,
        ),
        onPressed: () {
          context.pop();
          widget.onClose?.call();
        },
      ),
      title: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            UITextConstants.comments,
            style: TextStyle(
              fontSize: titleFontSize,
              fontWeight: FontWeight.w600,
              color: isDark 
                ? AppColors.dark.foregroundPrimary 
                : AppColors.light.foregroundPrimary,
            ),
          ),
          if (_listController.comments.isNotEmpty) ...[
            SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
            Text(
              '${_listController.comments.length}',
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
      centerTitle: true,
    );
  }

  /// 构建评论列表
  Widget _buildCommentList(BuildContext context, bool isDark) {
    return CommentList(
      comments: _listController.comments,
      config: widget.config,
      expandedReplies: _listController.expandedReplies,
      onToggleReplies: _onToggleReplies,
      onReply: _onReply,
      onLike: _onLike,
      onUserTap: _onUserTap,
      onLoadMore: _onLoadMore,
      hasMore: _listController.hasMore,
      isLoading: _listController.isLoading,
    );
  }

  /// 构建评论输入框
  Widget _buildCommentInput(BuildContext context, bool isDark) {
    return CommentInput(
      key: _inputKey,
      config: widget.config,
      replyTo: _replyTo,
      onSubmit: _onSubmitComment,
      onCancelReply: _onCancelReply,
    );
  }

  /// 切换回复展开状态
  void _onToggleReplies(String commentId) {
    setState(() {
      _listController.toggleReplyExpansion(commentId);
    });
  }

  /// 回复评论
  void _onReply(CommentModel comment) {
    setState(() {
      _replyTo = comment;
    });
    // 聚焦输入框
    FocusScope.of(context).requestFocus(FocusNode());
  }

  /// 取消回复
  void _onCancelReply() {
    setState(() {
      _replyTo = null;
    });
  }

  /// 点赞评论
  Future<void> _onLike(CommentModel comment) async {
    widget.onCommentLiked?.call(comment);
    
    // 先更新本地状态，提供即时反馈
    setState(() {
      _listController.updateComment(
        comment.copyWith(
          isLiked: !comment.isLiked,
          likes: comment.isLiked ? comment.likes - 1 : comment.likes + 1,
        ),
      );
    });

    try {
      final commentService = ref.read(commentServiceProvider);
      await commentService.toggleCommentLike(
        commentId: comment.id,
        isLiked: !comment.isLiked,
      );
    } catch (e) {
      // 如果请求失败，回滚本地状态
      if (mounted) {
        setState(() {
          _listController.updateComment(comment);
        });
        _showError('操作失败: ${e.toString()}');
      }
    }
  }

  /// 点击用户
  void _onUserTap(CommentModel comment) {
    widget.onUserTapped?.call(comment);
  }

  /// 加载更多
  void _onLoadMore() {
    _listController.setLoading(true);
    widget.onLoadMore?.call();
    
    // 模拟加载完成后重置状态
    Future.delayed(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _listController.setLoading(false);
          _listController.setHasMore(false);
        });
      }
    });
  }

  /// 提交评论
  Future<void> _onSubmitComment(String content) async {
    final validationError = CommentServiceUtils.validateCommentText(content);
    if (validationError != null) {
      _showError(validationError);
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final commentService = ref.read(commentServiceProvider);
      CommentModel newComment;

      if (_replyTo != null) {
        // 添加回复
        newComment = await commentService.addReply(
          postId: widget.postId,
          commentId: _replyTo!.id,
          text: content,
        );
        widget.onReplyAdded?.call(_replyTo!.id, content);
      } else {
        // 添加评论
        newComment = await commentService.addComment(
          postId: widget.postId,
          text: content,
        );
        widget.onCommentAdded?.call(content);
      }

      // 更新本地状态
      if (mounted) {
        setState(() {
          _listController.addComment(newComment);
          _replyTo = null;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        _showError('提交失败: ${e.toString()}');
      }
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

  /// 更新评论列表
  void updateComments(List<CommentModel> comments) {
    setState(() {
      _listController.setComments(comments);
    });
  }

  /// 添加评论
  void addComment(CommentModel comment) {
    setState(() {
      _listController.addComment(comment);
    });
  }

  /// 更新评论
  void updateComment(CommentModel comment) {
    setState(() {
      _listController.updateComment(comment);
    });
  }

  /// 删除评论
  void removeComment(String commentId) {
    setState(() {
      _listController.removeComment(commentId);
    });
  }
}

/// 评论查看器工具类
class CommentViewerUtils {
  /// 创建默认配置
  static CommentConfig createDefaultConfig({
    required String postId,
    required String postAuthorId,
    bool allowComments = true,
    bool isUserLoggedIn = false,
    bool isUserAuthor = false,
  }) {
    return CommentConfig(
      postId: postId,
      postAuthorId: postAuthorId,
      allowComments: allowComments,
      isUserLoggedIn: isUserLoggedIn,
      isUserAuthor: isUserAuthor,
    );
  }

  /// 计算评论总数（包括回复）
  static int calculateTotalComments(List<CommentModel> comments) {
    int total = comments.length;
    for (final comment in comments) {
      total += comment.replyCount;
    }
    return total;
  }

  /// 检查是否有新评论
  static bool hasNewComments(List<CommentModel> oldComments, List<CommentModel> newComments) {
    return newComments.length > oldComments.length;
  }
}
