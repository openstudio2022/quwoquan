import 'package:quwoquan_app/core/quwoquan_core.dart';
import '../comment_models.dart';

/// 评论API服务
/// 基于通用DataService实现评论相关的具体操作
class CommentApiService {
  final DataService _dataService;

  CommentApiService(this._dataService);

  /// 获取帖子的评论列表
  Future<List<CommentModel>> getPostComments({
    required String postId,
    int page = 1,
    int limit = 20,
  }) async {
    final results = await _dataService.getDataList(
      endpoint: 'comments',
      params: {'postId': postId},
      page: page,
      limit: limit,
    );
    
    return results.map((json) => CommentModel.fromJson(json)).toList();
  }

  /// 添加评论
  Future<CommentModel> addComment({
    required String postId,
    required String text,
    String? parentId,
  }) async {
    final result = await _dataService.createData(
      endpoint: 'comments',
      data: {
        'postId': postId,
        'text': text,
        'parentId': parentId,
        'createdAt': DateTime.now().toIso8601String(),
      },
    );
    
    return CommentModel.fromJson(result);
  }

  /// 添加回复
  Future<CommentModel> addReply({
    required String postId,
    required String commentId,
    required String text,
  }) async {
    final result = await _dataService.createData(
      endpoint: 'comments',
      data: {
        'postId': postId,
        'parentId': commentId,
        'text': text,
        'createdAt': DateTime.now().toIso8601String(),
      },
    );
    
    return CommentModel.fromJson(result);
  }

  /// 点赞/取消点赞评论
  Future<bool> toggleCommentLike({
    required String commentId,
    required bool isLiked,
  }) async {
    return await _dataService.executeAction(
      endpoint: 'comments',
      action: 'like',
      params: {
        'commentId': commentId,
        'isLiked': isLiked,
      },
    );
  }

  /// 删除评论
  Future<bool> deleteComment({
    required String commentId,
  }) async {
    return await _dataService.deleteData(
      endpoint: 'comments',
      id: commentId,
    );
  }

  /// 获取评论的回复列表
  Future<List<CommentModel>> getCommentReplies({
    required String commentId,
    int page = 1,
    int limit = 10,
  }) async {
    final results = await _dataService.getDataList(
      endpoint: 'comments',
      params: {'parentId': commentId},
      page: page,
      limit: limit,
    );
    
    return results.map((json) => CommentModel.fromJson(json)).toList();
  }
}
