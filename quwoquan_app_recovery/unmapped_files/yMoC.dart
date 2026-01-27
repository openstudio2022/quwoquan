import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_api_service.dart';
import 'comment_mock_service.dart';

/// 评论服务提供者
/// 根据配置返回API或Mock实现
final commentServiceProvider = Provider<CommentApiService>((ref) {
  final dataService = ref.watch(dataServiceProvider);
  return CommentApiService(dataService);
});

/// Mock评论服务提供者
final commentMockServiceProvider = Provider<CommentMockService>((ref) {
  return CommentMockService();
});

/// 评论服务工厂
class CommentServiceFactory {
  /// 创建评论服务
  static CommentApiService createApiService(DataService dataService) {
    return CommentApiService(dataService);
  }
  
  /// 创建Mock评论服务
  static CommentMockService createMockService() {
    return CommentMockService();
  }
}
