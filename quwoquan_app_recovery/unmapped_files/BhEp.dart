import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';

/// 评论服务具体实现
/// 使用CommentModel作为具体类型，基于通用DataService
class CommentServiceImpl {
  final DataService _baseService;

  CommentServiceImpl(this._baseService);

  @override
  Future<List<CommentModel>> getPostComments({
    required String postId,
    int page = 1,
    int limit = 20,
  }) async {
    final results = await _baseService.getDataList(
      endpoint: '/comments',
      params: {'postId': postId},
      page: page,
      limit: limit,
    );
    
    // 将Map转换为CommentModel
    return results.map((json) => CommentModel.fromJson(json)).toList();
  }

  @override
  Future<CommentModel> addComment({
    required String postId,
    required String text,
    String? parentId,
  }) async {
    final result = await _baseService.createData(
      endpoint: '/comments',
      data: {
        'postId': postId,
        'text': text,
        'parentId': parentId,
      },
    );
    
    return CommentModel.fromJson(result);
  }

  @override
  Future<CommentModel> addReply({
    required String postId,
    required String commentId,
    required String text,
  }) async {
    final result = await _baseService.createData(
      endpoint: '/comments/$commentId/replies',
      data: {
        'postId': postId,
        'text': text,
      },
    );
    
    return CommentModel.fromJson(result);
  }

  @override
  Future<bool> toggleCommentLike({
    required String commentId,
    required bool isLiked,
  }) async {
    return await _baseService.executeAction(
      endpoint: '/comments',
      action: 'toggleLike',
      params: {
        'commentId': commentId,
        'isLiked': isLiked,
      },
    );
  }

  @override
  Future<bool> deleteComment({
    required String commentId,
  }) async {
    return await _baseService.deleteData(
      endpoint: '/comments',
      id: commentId,
    );
  }

  @override
  Future<List<CommentModel>> getCommentReplies({
    required String commentId,
    int page = 1,
    int limit = 10,
  }) async {
    final results = await _baseService.getDataList(
      endpoint: '/comments/$commentId/replies',
      page: page,
      limit: limit,
    );
    
    return results.map((json) => CommentModel.fromJson(json)).toList();
  }

  @override
  bool get isAvailable => _baseService.isAvailable;
}

/// 评论服务提供者 - 使用具体类型
final commentServiceProvider = Provider<CommentServiceImpl>((ref) {
  final baseService = ref.watch(dataServiceProvider);
  return CommentServiceImpl(baseService);
});
