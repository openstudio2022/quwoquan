import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';
import 'package:quwoquan_app/features/home/models/post_models.dart';

/// 用户API服务
/// 基于通用DataService实现用户相关的具体操作
class UserApiService {
  final DataService _dataService;

  UserApiService(this._dataService);

  /// 根据用户名获取用户信息
  Future<User?> getUserByUsername(String username) async {
    final result = await _dataService.getDataItem(
      endpoint: 'users',
      id: username,
    );
    
    return result != null ? User.fromJson(result) : null;
  }
  
  /// 获取用户发布的帖子
  Future<List<Post>> getUserPosts(String username, {int page = 1, int limit = 10}) async {
    final results = await _dataService.getDataList(
      endpoint: 'users/$username/posts',
      page: page,
      limit: limit,
    );
    
    return results.map((json) => Post.fromJson(json)).toList();
  }
  
  /// 获取用户作品网格
  Future<List<String>> getUserPostsGrid(String username) async {
    final results = await _dataService.getDataList(
      endpoint: 'users/$username/posts/grid',
    );
    
    return results.map((json) => json['imageUrl'] as String).toList();
  }
  
  /// 关注用户
  Future<bool> followUser(String userId) async {
    return await _dataService.executeAction(
      endpoint: 'users',
      action: 'follow',
      params: {'userId': userId},
    );
  }
  
  /// 取消关注用户
  Future<bool> unfollowUser(String userId) async {
    return await _dataService.executeAction(
      endpoint: 'users',
      action: 'unfollow',
      params: {'userId': userId},
    );
  }
}
