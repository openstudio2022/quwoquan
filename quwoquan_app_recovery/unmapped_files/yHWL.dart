import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/data/models/user_model.dart';
import 'package:quwoquan_app/core/data/models/post_model.dart';
import 'package:quwoquan_app/core/data/models/api_response.dart';

/// 数据服务基础接口
abstract class DataService {
  Future<ApiResponse<List<User>>> getUsers();
  Future<ApiResponse<List<Post>>> getPosts({String? category, int limit = 20});
  Future<ApiResponse<User>> getUserProfile(String username);
  Future<ApiResponse<List<Post>>> getUserPosts(String username);
  Future<ApiResponse<List<User>>> searchUsers(String query);
  Future<ApiResponse<List<Post>>> searchPosts(String query);
}

/// 数据服务配置
class DataServiceConfig {
  final bool useMockData;
  final String? apiBaseUrl;
  final Map<String, String>? headers;

  const DataServiceConfig({
    this.useMockData = true,
    this.apiBaseUrl,
    this.headers,
  });
}

/// 数据服务工厂
class DataServiceFactory {
  static DataService create(DataServiceConfig config) {
    if (config.useMockData) {
      return MockDataService();
    } else {
      return ApiDataService(
        baseUrl: config.apiBaseUrl ?? 'https://api.quwoquan.com',
        headers: config.headers,
      );
    }
  }
}

/// 数据服务配置提供者
final dataServiceConfigProvider = Provider<DataServiceConfig>((ref) {
  return const DataServiceConfig(
    useMockData: true, // 默认使用mock数据
  );
});

/// 数据服务提供者
final dataServiceProvider = Provider<DataService>((ref) {
  final config = ref.watch(dataServiceConfigProvider);
  return DataServiceFactory.create(config);
});

/// Mock数据服务
class MockDataService implements DataService {
  @override
  Future<ApiResponse<List<User>>> getUsers() async {
    await Future.delayed(const Duration(milliseconds: 500));
    
    final users = [
      User(
        id: '1',
        username: 'test_user_1',
        displayName: '测试用户1',
        avatar: 'https://via.placeholder.com/150',
        bio: '这是一个测试用户',
        followers: 100,
        following: 50,
        postsGrid: [],
        categorizedPosts: {},
      ),
      User(
        id: '2',
        username: 'test_user_2',
        displayName: '测试用户2',
        avatar: 'https://via.placeholder.com/150',
        bio: '这是另一个测试用户',
        followers: 200,
        following: 80,
        postsGrid: [],
        categorizedPosts: {},
      ),
    ];
    
    return ApiResponse<List<User>>(
      success: true,
      data: users,
      message: '获取用户列表成功',
      total: users.length,
      page: 1,
      hasMore: false,
    );
  }

  @override
  Future<ApiResponse<List<Post>>> getPosts({String? category, int limit = 20}) async {
    await Future.delayed(const Duration(milliseconds: 300));
    
    final posts = List.generate(limit, (index) {
      return Post(
        id: 'post_$index',
        username: 'test_user_${index % 3 + 1}',
        images: ['https://via.placeholder.com/400x400'],
        caption: '这是第${index + 1}个测试帖子',
        likes: (index + 1) * 10,
        comments: (index + 1) * 3,
        publisher: User(
          id: '${index % 3 + 1}',
          username: 'test_user_${index % 3 + 1}',
          displayName: '测试用户${index % 3 + 1}',
          avatar: 'https://via.placeholder.com/150',
          bio: '测试用户简介',
          followers: (index + 1) * 50,
          following: (index + 1) * 20,
          postsGrid: [],
          categorizedPosts: {},
        ),
      );
    });
    
    return ApiResponse<List<Post>>(
      success: true,
      data: posts,
      message: '获取帖子列表成功',
      total: posts.length,
      page: 1,
      hasMore: false,
    );
  }

  @override
  Future<ApiResponse<User>> getUserProfile(String username) async {
    await Future.delayed(const Duration(milliseconds: 400));
    
    final user = User(
      id: '1',
      username: username,
      displayName: '用户$username',
      avatar: 'https://via.placeholder.com/150',
      bio: '这是用户$username的简介',
      followers: 150,
      following: 60,
      postsGrid: [],
      categorizedPosts: {},
    );
    
    return ApiResponse<User>(
      success: true,
      data: user,
      message: '获取用户信息成功',
    );
  }

  @override
  Future<ApiResponse<List<Post>>> getUserPosts(String username) async {
    await Future.delayed(const Duration(milliseconds: 350));
    
    final posts = List.generate(5, (index) {
      return Post(
        id: 'user_post_$index',
        username: username,
        images: ['https://via.placeholder.com/400x400'],
        caption: '用户$username的第${index + 1}个帖子',
        likes: (index + 1) * 5,
        comments: index + 1,
        publisher: User(
          id: '1',
          username: username,
          displayName: '用户$username',
          avatar: 'https://via.placeholder.com/150',
          bio: '用户简介',
          followers: 100,
          following: 50,
          postsGrid: [],
          categorizedPosts: {},
        ),
      );
    });
    
    return ApiResponse<List<Post>>(
      success: true,
      data: posts,
      message: '获取用户帖子成功',
      total: posts.length,
      page: 1,
      hasMore: false,
    );
  }

  @override
  Future<ApiResponse<List<User>>> searchUsers(String query) async {
    await Future.delayed(const Duration(milliseconds: 200));
    
    final users = [
      User(
        id: 'search_1',
        username: 'search_user_1',
        displayName: '搜索用户1',
        avatar: 'https://via.placeholder.com/150',
        bio: '包含$query的用户',
        followers: 80,
        following: 30,
        postsGrid: [],
        categorizedPosts: {},
      ),
    ];
    
    return ApiResponse<List<User>>(
      success: true,
      data: users,
      message: '搜索用户成功',
      total: users.length,
      page: 1,
      hasMore: false,
    );
  }

  @override
  Future<ApiResponse<List<Post>>> searchPosts(String query) async {
    await Future.delayed(const Duration(milliseconds: 250));
    
    final posts = [
      Post(
        id: 'search_post_1',
        username: 'search_user',
        images: ['https://via.placeholder.com/400x400'],
        caption: '包含$query的帖子内容',
        likes: 25,
        comments: 5,
        publisher: User(
          id: 'search_1',
          username: 'search_user',
          displayName: '搜索用户',
          avatar: 'https://via.placeholder.com/150',
          bio: '搜索用户简介',
          followers: 60,
          following: 25,
          postsGrid: [],
          categorizedPosts: {},
        ),
      ),
    ];
    
    return ApiResponse<List<Post>>(
      success: true,
      data: posts,
      message: '搜索帖子成功',
      total: posts.length,
      page: 1,
      hasMore: false,
    );
  }
}

/// API数据服务
class ApiDataService implements DataService {
  final String baseUrl;
  final Map<String, String>? headers;

  ApiDataService({
    required this.baseUrl,
    this.headers,
  });

  @override
  Future<ApiResponse<List<User>>> getUsers() async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }

  @override
  Future<ApiResponse<List<Post>>> getPosts({String? category, int limit = 20}) async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }

  @override
  Future<ApiResponse<User>> getUserProfile(String username) async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }

  @override
  Future<ApiResponse<List<Post>>> getUserPosts(String username) async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }

  @override
  Future<ApiResponse<List<User>>> searchUsers(String query) async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }

  @override
  Future<ApiResponse<List<Post>>> searchPosts(String query) async {
    // TODO: 实现真实的API调用
    throw UnimplementedError('API数据服务尚未实现');
  }
}
