# 趣我圈App 测试规则

## 📋 文档概述

### 基本信息
- **项目名称**: 趣我圈 (QuWoQuan)
- **文档版本**: v1.0
- **创建日期**: 2024年12月19日
- **适用范围**: 趣我圈App端侧和云侧测试
- **测试框架**: Flutter Test, Mockito, Integration Test, Golden Test

### 测试原则
- **全面性**: 覆盖所有功能模块
- **自动化**: 最大化自动化测试比例
- **持续性**: 集成到CI/CD流程
- **质量导向**: 确保产品质量
- **效率优先**: 提高测试效率

## 🧪 测试体系架构

### 1. 测试金字塔

#### 1.1 测试层级
```yaml
测试层级:
  单元测试 (Unit Tests):
    比例: 70%
    目标: 业务逻辑、工具类、服务类
    框架: Flutter Test, Mockito
    覆盖率: >80%

  Widget测试 (Widget Tests):
    比例: 20%
    目标: UI组件、用户交互
    框架: Flutter Test
    覆盖率: >70%

  集成测试 (Integration Tests):
    比例: 10%
    目标: 端到端功能、API集成
    框架: Integration Test
    覆盖率: >60%
```

#### 1.2 测试策略
```yaml
测试策略:
  分层测试:
    - 单元测试: 快速反馈
    - Widget测试: UI验证
    - 集成测试: 功能验证
    - E2E测试: 用户场景

  并行测试:
    - 多环境并行
    - 多设备并行
    - 多版本并行
    - 多配置并行

  持续测试:
    - 代码提交触发
    - 定时执行
    - 手动触发
    - 发布前验证
```

### 2. 测试环境

#### 2.1 测试环境配置
```yaml
环境配置:
  开发环境:
    用途: 开发阶段测试
    数据: Mock数据
    配置: 开发配置
    监控: 基础监控

  测试环境:
    用途: 功能测试
    数据: 测试数据
    配置: 测试配置
    监控: 完整监控

  预生产环境:
    用途: 发布前验证
    数据: 生产数据副本
    配置: 生产配置
    监控: 生产级监控

  生产环境:
    用途: 线上监控
    数据: 真实数据
    配置: 生产配置
    监控: 完整监控
```

#### 2.2 测试数据管理
```yaml
数据管理:
  测试数据:
    - 用户数据: 测试用户账号
    - 内容数据: 测试内容
    - 配置数据: 测试配置
    - 元数据: 测试元数据

  数据隔离:
    - 环境隔离
    - 用户隔离
    - 数据隔离
    - 配置隔离

  数据清理:
    - 自动清理
    - 定期清理
    - 手动清理
    - 备份恢复
```

## 🔬 单元测试规则

### 1. 单元测试规范

#### 1.1 测试用例设计
```dart
// 单元测试示例
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

import '../lib/features/home/models/post.dart';
import '../lib/features/home/services/post_service.dart';
import '../lib/features/home/providers/home_provider.dart';

// 生成Mock类
@GenerateMocks([PostService])
import 'home_provider_test.mocks.dart';

void main() {
  group('HomeProvider Tests', () {
    late MockPostService mockPostService;
    late HomeNotifier homeNotifier;
    
    setUp(() {
      mockPostService = MockPostService();
      homeNotifier = HomeNotifier(mockPostService);
    });
    
    tearDown(() {
      // 清理资源
    });
    
    test('should load posts successfully', () async {
      // Arrange
      final mockPosts = [
        Post(id: '1', title: 'Test Post 1', content: 'Content 1'),
        Post(id: '2', title: 'Test Post 2', content: 'Content 2'),
      ];
      when(mockPostService.getPosts(page: 1))
          .thenAnswer((_) async => mockPosts);
      
      // Act
      await homeNotifier.loadPosts();
      
      // Assert
      expect(homeNotifier.state.posts, equals(mockPosts));
      expect(homeNotifier.state.isLoading, isFalse);
      expect(homeNotifier.state.error, isNull);
      verify(mockPostService.getPosts(page: 1)).called(1);
    });
    
    test('should handle error when loading posts fails', () async {
      // Arrange
      const errorMessage = 'Network error';
      when(mockPostService.getPosts(page: 1))
          .thenThrow(Exception(errorMessage));
      
      // Act
      await homeNotifier.loadPosts();
      
      // Assert
      expect(homeNotifier.state.posts, isEmpty);
      expect(homeNotifier.state.isLoading, isFalse);
      expect(homeNotifier.state.error, equals(errorMessage));
    });
    
    test('should refresh posts successfully', () async {
      // Arrange
      final initialPosts = [
        Post(id: '1', title: 'Initial Post', content: 'Initial Content'),
      ];
      final refreshedPosts = [
        Post(id: '2', title: 'Refreshed Post', content: 'Refreshed Content'),
      ];
      
      when(mockPostService.getPosts(page: 1))
          .thenAnswer((_) async => refreshedPosts);
      
      homeNotifier.state = homeNotifier.state.copyWith(posts: initialPosts);
      
      // Act
      await homeNotifier.refreshPosts();
      
      // Assert
      expect(homeNotifier.state.posts, equals(refreshedPosts));
      expect(homeNotifier.state.currentPage, equals(2));
      expect(homeNotifier.state.hasMore, isTrue);
    });
  });
}
```

#### 1.2 测试用例规范
```yaml
测试用例规范:
  命名规范:
    - 描述性命名
    - 行为驱动命名
    - 场景+期望结果
    - 使用should/when/then模式

  结构规范:
    - Arrange: 准备测试数据
    - Act: 执行被测试方法
    - Assert: 验证结果
    - Cleanup: 清理资源

  覆盖范围:
    - 正常流程测试
    - 异常流程测试
    - 边界条件测试
    - 参数验证测试
    - 状态变化测试
```

#### 1.3 Mock使用规范
```dart
// Mock类定义
@GenerateMocks([
  PostService,
  UserService,
  AnalyticsService,
  StorageService,
])
import 'test_mocks.mocks.dart';

// Mock使用示例
class PostServiceTest {
  late MockPostService mockPostService;
  late MockUserService mockUserService;
  
  setUp(() {
    mockPostService = MockPostService();
    mockUserService = MockUserService();
  });
  
  test('should create post with valid data', () async {
    // Arrange
    final mockUser = User(id: '1', name: 'Test User');
    final mockPost = Post(
      id: '1',
      title: 'Test Post',
      content: 'Test Content',
      authorId: '1',
    );
    
    when(mockUserService.getCurrentUser())
        .thenAnswer((_) async => mockUser);
    when(mockPostService.createPost(any))
        .thenAnswer((_) async => mockPost);
    
    // Act
    final result = await postService.createPost({
      'title': 'Test Post',
      'content': 'Test Content',
    });
    
    // Assert
    expect(result, equals(mockPost));
    verify(mockUserService.getCurrentUser()).called(1);
    verify(mockPostService.createPost(any)).called(1);
  });
}
```

### 2. 业务逻辑测试

#### 2.1 状态管理测试
```dart
// 状态管理测试
class HomeStateTest {
  test('should update loading state correctly', () {
    // Arrange
    final initialState = HomeState(
      isLoading: false,
      posts: [],
      error: null,
    );
    
    // Act
    final loadingState = initialState.copyWith(isLoading: true);
    final loadedState = loadingState.copyWith(
      isLoading: false,
      posts: [Post(id: '1', title: 'Test')],
    );
    
    // Assert
    expect(loadingState.isLoading, isTrue);
    expect(loadedState.isLoading, isFalse);
    expect(loadedState.posts.length, equals(1));
  });
  
  test('should handle error state correctly', () {
    // Arrange
    const errorMessage = 'Network error';
    final initialState = HomeState(
      isLoading: false,
      posts: [],
      error: null,
    );
    
    // Act
    final errorState = initialState.copyWith(error: errorMessage);
    final clearedState = errorState.copyWith(error: null);
    
    // Assert
    expect(errorState.error, equals(errorMessage));
    expect(clearedState.error, isNull);
  });
}
```

#### 2.2 服务层测试
```dart
// 服务层测试
class PostServiceTest {
  late MockHttpClient mockHttpClient;
  late PostService postService;
  
  setUp(() {
    mockHttpClient = MockHttpClient();
    postService = PostService(mockHttpClient);
  });
  
  test('should fetch posts successfully', () async {
    // Arrange
    final mockResponse = {
      'posts': [
        {'id': '1', 'title': 'Test Post', 'content': 'Test Content'},
      ],
      'pagination': {'page': 1, 'hasMore': true},
    };
    
    when(mockHttpClient.get('/posts?page=1'))
        .thenAnswer((_) async => Response(
          data: mockResponse,
          statusCode: 200,
          requestOptions: RequestOptions(path: '/posts'),
        ));
    
    // Act
    final result = await postService.getPosts(page: 1);
    
    // Assert
    expect(result.posts.length, equals(1));
    expect(result.posts.first.title, equals('Test Post'));
    expect(result.pagination.hasMore, isTrue);
  });
  
  test('should handle network error', () async {
    // Arrange
    when(mockHttpClient.get('/posts?page=1'))
        .thenThrow(SocketException('No internet connection'));
    
    // Act & Assert
    expect(
      () => postService.getPosts(page: 1),
      throwsA(isA<NetworkException>()),
    );
  });
}
```

## 🎨 Widget测试规则

### 1. Widget测试规范

#### 1.1 组件测试
```dart
// Widget测试示例
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../lib/features/home/widgets/post_card.dart';
import '../lib/features/home/models/post.dart';

void main() {
  group('PostCard Widget Tests', () {
    testWidgets('should display post information correctly', (tester) async {
      // Arrange
      final post = Post(
        id: '1',
        title: 'Test Post',
        content: 'Test Content',
        authorName: 'Test Author',
        createdAt: DateTime.now(),
      );
      
      // Act
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: PostCard(post: post),
            ),
          ),
        ),
      );
      
      // Assert
      expect(find.text('Test Post'), findsOneWidget);
      expect(find.text('Test Content'), findsOneWidget);
      expect(find.text('Test Author'), findsOneWidget);
    });
    
    testWidgets('should handle tap event correctly', (tester) async {
      // Arrange
      final post = Post(id: '1', title: 'Test Post', content: 'Test Content');
      bool tapped = false;
      
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: PostCard(
                post: post,
                onTap: () => tapped = true,
              ),
            ),
          ),
        ),
      );
      
      // Act
      await tester.tap(find.byType(PostCard));
      await tester.pump();
      
      // Assert
      expect(tapped, isTrue);
    });
    
    testWidgets('should show loading state correctly', (tester) async {
      // Arrange
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            home: Scaffold(
              body: PostCard(
                post: null,
                isLoading: true,
              ),
            ),
          ),
        ),
      );
      
      // Assert
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });
  });
}
```

#### 1.2 交互测试
```dart
// 交互测试示例
class PostCardInteractionTest {
  testWidgets('should handle like button tap', (tester) async {
    // Arrange
    final post = Post(id: '1', title: 'Test Post', content: 'Test Content');
    bool liked = false;
    
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: PostCard(
              post: post,
              onLike: () => liked = true,
            ),
          ),
        ),
      ),
    );
    
    // Act
    await tester.tap(find.byIcon(Icons.favorite_border));
    await tester.pump();
    
    // Assert
    expect(liked, isTrue);
    expect(find.byIcon(Icons.favorite), findsOneWidget);
  });
  
  testWidgets('should handle comment button tap', (tester) async {
    // Arrange
    final post = Post(id: '1', title: 'Test Post', content: 'Test Content');
    bool commentTapped = false;
    
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: PostCard(
              post: post,
              onComment: () => commentTapped = true,
            ),
          ),
        ),
      ),
    );
    
    // Act
    await tester.tap(find.byIcon(Icons.comment));
    await tester.pump();
    
    // Assert
    expect(commentTapped, isTrue);
  });
}
```

### 2. 页面测试

#### 2.1 页面渲染测试
```dart
// 页面渲染测试
class HomePageTest {
  testWidgets('should render home page correctly', (tester) async {
    // Arrange
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: HomePage(),
        ),
      ),
    );
    
    // Assert
    expect(find.byType(AppBar), findsOneWidget);
    expect(find.byType(BottomNavigationBar), findsOneWidget);
    expect(find.text('首页'), findsOneWidget);
  });
  
  testWidgets('should navigate between tabs correctly', (tester) async {
    // Arrange
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: HomePage(),
        ),
      ),
    );
    
    // Act
    await tester.tap(find.text('搜索'));
    await tester.pumpAndSettle();
    
    // Assert
    expect(find.text('搜索'), findsOneWidget);
    expect(find.byType(SearchPage), findsOneWidget);
  });
}
```

## 🔗 接口测试规则

### 1. API测试

#### 1.1 HTTP接口测试
```dart
// API接口测试
class ApiTest {
  late MockDio mockDio;
  late ApiService apiService;
  
  setUp(() {
    mockDio = MockDio();
    apiService = ApiService(mockDio);
  });
  
  test('should get posts successfully', () async {
    // Arrange
    final mockResponse = {
      'posts': [
        {'id': '1', 'title': 'Test Post', 'content': 'Test Content'},
      ],
      'pagination': {'page': 1, 'hasMore': true},
    };
    
    when(mockDio.get('/posts', queryParameters: {'page': 1}))
        .thenAnswer((_) async => Response(
          data: mockResponse,
          statusCode: 200,
          requestOptions: RequestOptions(path: '/posts'),
        ));
    
    // Act
    final result = await apiService.getPosts(page: 1);
    
    // Assert
    expect(result.posts.length, equals(1));
    expect(result.posts.first.title, equals('Test Post'));
    expect(result.pagination.hasMore, isTrue);
  });
  
  test('should handle 404 error', () async {
    // Arrange
    when(mockDio.get('/posts/999'))
        .thenAnswer((_) async => Response(
          data: {'error': 'Post not found'},
          statusCode: 404,
          requestOptions: RequestOptions(path: '/posts/999'),
        ));
    
    // Act & Assert
    expect(
      () => apiService.getPost('999'),
      throwsA(isA<NotFoundException>()),
    );
  });
  
  test('should handle network timeout', () async {
    // Arrange
    when(mockDio.get('/posts'))
        .thenThrow(DioError(
          requestOptions: RequestOptions(path: '/posts'),
          type: DioErrorType.connectTimeout,
        ));
    
    // Act & Assert
    expect(
      () => apiService.getPosts(),
      throwsA(isA<NetworkException>()),
    );
  });
}
```

#### 1.2 数据模型测试
```dart
// 数据模型测试
class PostModelTest {
  test('should create Post from JSON correctly', () {
    // Arrange
    final json = {
      'id': '1',
      'title': 'Test Post',
      'content': 'Test Content',
      'authorId': 'user1',
      'createdAt': '2024-01-01T00:00:00Z',
      'likes': 10,
      'comments': 5,
    };
    
    // Act
    final post = Post.fromJson(json);
    
    // Assert
    expect(post.id, equals('1'));
    expect(post.title, equals('Test Post'));
    expect(post.content, equals('Test Content'));
    expect(post.authorId, equals('user1'));
    expect(post.likes, equals(10));
    expect(post.comments, equals(5));
  });
  
  test('should convert Post to JSON correctly', () {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Test Post',
      content: 'Test Content',
      authorId: 'user1',
      createdAt: DateTime.parse('2024-01-01T00:00:00Z'),
      likes: 10,
      comments: 5,
    );
    
    // Act
    final json = post.toJson();
    
    // Assert
    expect(json['id'], equals('1'));
    expect(json['title'], equals('Test Post'));
    expect(json['content'], equals('Test Content'));
    expect(json['authorId'], equals('user1'));
    expect(json['likes'], equals(10));
    expect(json['comments'], equals(5));
  });
  
  test('should handle missing fields gracefully', () {
    // Arrange
    final json = {
      'id': '1',
      'title': 'Test Post',
      // Missing other fields
    };
    
    // Act
    final post = Post.fromJson(json);
    
    // Assert
    expect(post.id, equals('1'));
    expect(post.title, equals('Test Post'));
    expect(post.content, isEmpty);
    expect(post.likes, equals(0));
    expect(post.comments, equals(0));
  });
}
```

### 2. 数据库测试

#### 2.1 数据库操作测试
```dart
// 数据库测试
class DatabaseTest {
  late Database database;
  
  setUp(() async {
    database = await openDatabase(
      inMemoryDatabasePath,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            authorId TEXT NOT NULL,
            createdAt INTEGER NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0
          )
        ''');
      },
    );
  });
  
  tearDown(() async {
    await database.close();
  });
  
  test('should insert post correctly', () async {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Test Post',
      content: 'Test Content',
      authorId: 'user1',
      createdAt: DateTime.now(),
    );
    
    // Act
    await database.insert('posts', post.toJson());
    
    // Assert
    final result = await database.query('posts', where: 'id = ?', whereArgs: ['1']);
    expect(result.length, equals(1));
    expect(result.first['title'], equals('Test Post'));
  });
  
  test('should update post correctly', () async {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Original Title',
      content: 'Original Content',
      authorId: 'user1',
      createdAt: DateTime.now(),
    );
    
    await database.insert('posts', post.toJson());
    
    // Act
    await database.update(
      'posts',
      {'title': 'Updated Title'},
      where: 'id = ?',
      whereArgs: ['1'],
    );
    
    // Assert
    final result = await database.query('posts', where: 'id = ?', whereArgs: ['1']);
    expect(result.first['title'], equals('Updated Title'));
  });
  
  test('should delete post correctly', () async {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Test Post',
      content: 'Test Content',
      authorId: 'user1',
      createdAt: DateTime.now(),
    );
    
    await database.insert('posts', post.toJson());
    
    // Act
    await database.delete('posts', where: 'id = ?', whereArgs: ['1']);
    
    // Assert
    final result = await database.query('posts', where: 'id = ?', whereArgs: ['1']);
    expect(result.length, equals(0));
  });
}
```

## ⚡ 性能测试规则

### 1. 性能测试规范

#### 1.1 响应时间测试
```dart
// 性能测试示例
class PerformanceTest {
  test('should load posts within acceptable time', () async {
    // Arrange
    final stopwatch = Stopwatch()..start();
    
    // Act
    final posts = await postService.getPosts();
    stopwatch.stop();
    
    // Assert
    expect(stopwatch.elapsedMilliseconds, lessThan(1000)); // 1秒内
    expect(posts.length, greaterThan(0));
  });
  
  test('should render large list efficiently', () async {
    // Arrange
    final largePostList = List.generate(1000, (index) => 
      Post(id: '$index', title: 'Post $index', content: 'Content $index')
    );
    
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: ListView.builder(
              itemCount: largePostList.length,
              itemBuilder: (context, index) => PostCard(post: largePostList[index]),
            ),
          ),
        ),
      ),
    );
    
    // Act
    final stopwatch = Stopwatch()..start();
    await tester.pumpAndSettle();
    stopwatch.stop();
    
    // Assert
    expect(stopwatch.elapsedMilliseconds, lessThan(2000)); // 2秒内
  });
}
```

#### 1.2 内存使用测试
```dart
// 内存测试
class MemoryTest {
  test('should not have memory leaks', () async {
    // Arrange
    final initialMemory = await _getMemoryUsage();
    
    // Act - 创建大量对象
    for (int i = 0; i < 1000; i++) {
      final post = Post(
        id: '$i',
        title: 'Post $i',
        content: 'Content $i',
        authorId: 'user$i',
        createdAt: DateTime.now(),
      );
      // 使用post对象
      _processPost(post);
    }
    
    // 强制垃圾回收
    await Future.delayed(Duration(milliseconds: 100));
    
    // Assert
    final finalMemory = await _getMemoryUsage();
    final memoryIncrease = finalMemory - initialMemory;
    
    expect(memoryIncrease, lessThan(10 * 1024 * 1024)); // 增加不超过10MB
  });
  
  Future<int> _getMemoryUsage() async {
    // 获取内存使用量的实现
    return 0;
  }
  
  void _processPost(Post post) {
    // 处理post对象的逻辑
  }
}
```

### 2. 压力测试

#### 2.1 并发测试
```dart
// 并发测试
class ConcurrencyTest {
  test('should handle concurrent requests', () async {
    // Arrange
    const concurrentRequests = 100;
    final futures = <Future>[];
    
    // Act
    for (int i = 0; i < concurrentRequests; i++) {
      futures.add(postService.getPosts(page: 1));
    }
    
    final results = await Future.wait(futures);
    
    // Assert
    expect(results.length, equals(concurrentRequests));
    for (final result in results) {
      expect(result, isA<List<Post>>());
      expect(result.isNotEmpty, isTrue);
    }
  });
  
  test('should handle rapid user interactions', () async {
    // Arrange
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: HomePage(),
        ),
      ),
    );
    
    // Act - 快速点击
    for (int i = 0; i < 10; i++) {
      await tester.tap(find.byType(FloatingActionButton));
      await tester.pump(Duration(milliseconds: 50));
    }
    
    // Assert - 应用不应该崩溃
    expect(tester.takeException(), isNull);
  });
}
```

## 🔒 安全测试规则

### 1. 安全测试规范

#### 1.1 输入验证测试
```dart
// 输入验证测试
class SecurityTest {
  test('should validate user input correctly', () {
    // Arrange
    const validEmail = 'test@example.com';
    const invalidEmail = 'invalid-email';
    const validPassword = 'Password123!';
    const invalidPassword = '123';
    
    // Act & Assert
    expect(InputValidator.validateEmail(validEmail), isNull);
    expect(InputValidator.validateEmail(invalidEmail), isNotNull);
    expect(InputValidator.validatePassword(validPassword), isNull);
    expect(InputValidator.validatePassword(invalidPassword), isNotNull);
  });
  
  test('should prevent SQL injection', () async {
    // Arrange
    const maliciousInput = "'; DROP TABLE users; --";
    
    // Act
    final result = await database.query(
      'SELECT * FROM users WHERE name = ?',
      whereArgs: [maliciousInput],
    );
    
    // Assert
    expect(result, isEmpty);
    // 验证表没有被删除
    final tableExists = await database.rawQuery(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    );
    expect(tableExists.isNotEmpty, isTrue);
  });
  
  test('should prevent XSS attacks', () {
    // Arrange
    const maliciousScript = '<script>alert("XSS")</script>';
    
    // Act
    final sanitized = HtmlSanitizer.sanitize(maliciousScript);
    
    // Assert
    expect(sanitized.contains('<script>'), isFalse);
    expect(sanitized.contains('alert'), isFalse);
  });
}
```

#### 1.2 权限测试
```dart
// 权限测试
class PermissionTest {
  test('should require authentication for protected routes', () async {
    // Arrange
    final unauthenticatedUser = User(id: null, name: 'Guest');
    
    // Act
    final result = await postService.createPost(
      {'title': 'Test Post', 'content': 'Test Content'},
      user: unauthenticatedUser,
    );
    
    // Assert
    expect(result, isNull);
    expect(logger.lastError, contains('Authentication required'));
  });
  
  test('should prevent unauthorized access to user data', () async {
    // Arrange
    final user1 = User(id: 'user1', name: 'User 1');
    final user2 = User(id: 'user2', name: 'User 2');
    
    // Act
    final result = await userService.getUserPosts('user1', requestingUser: user2);
    
    // Assert
    expect(result, isEmpty);
    expect(logger.lastWarning, contains('Unauthorized access'));
  });
}
```

### 2. 数据安全测试

#### 2.1 加密测试
```dart
// 加密测试
class EncryptionTest {
  test('should encrypt sensitive data correctly', () {
    // Arrange
    const sensitiveData = 'password123';
    const key = 'encryption-key';
    
    // Act
    final encrypted = EncryptionUtils.encrypt(sensitiveData, key);
    final decrypted = EncryptionUtils.decrypt(encrypted, key);
    
    // Assert
    expect(encrypted, isNot(equals(sensitiveData)));
    expect(decrypted, equals(sensitiveData));
    expect(encrypted.length, greaterThan(sensitiveData.length));
  });
  
  test('should hash passwords correctly', () {
    // Arrange
    const password = 'password123';
    
    // Act
    final hash1 = PasswordUtils.hash(password);
    final hash2 = PasswordUtils.hash(password);
    final isValid = PasswordUtils.verify(password, hash1);
    
    // Assert
    expect(hash1, isNot(equals(password)));
    expect(hash1, equals(hash2)); // 相同密码应该产生相同哈希
    expect(isValid, isTrue);
  });
}
```

## 🔄 集成测试规则

### 1. 端到端测试

#### 1.1 用户场景测试
```dart
// 集成测试示例
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  
  group('User Journey Tests', () {
    testWidgets('should complete post creation flow', (tester) async {
      // Arrange
      await tester.pumpWidget(MyApp());
      await tester.pumpAndSettle();
      
      // Act - 登录
      await tester.tap(find.text('登录'));
      await tester.pumpAndSettle();
      
      await tester.enterText(find.byType(TextField).first, 'test@example.com');
      await tester.enterText(find.byType(TextField).last, 'password123');
      await tester.tap(find.text('登录'));
      await tester.pumpAndSettle();
      
      // Act - 创建帖子
      await tester.tap(find.byIcon(Icons.add));
      await tester.pumpAndSettle();
      
      await tester.enterText(find.byType(TextField).first, 'Test Post Title');
      await tester.enterText(find.byType(TextField).last, 'Test Post Content');
      await tester.tap(find.text('发布'));
      await tester.pumpAndSettle();
      
      // Assert
      expect(find.text('Test Post Title'), findsOneWidget);
      expect(find.text('Test Post Content'), findsOneWidget);
      expect(find.text('发布成功'), findsOneWidget);
    });
    
    testWidgets('should complete search flow', (tester) async {
      // Arrange
      await tester.pumpWidget(MyApp());
      await tester.pumpAndSettle();
      
      // Act - 导航到搜索页
      await tester.tap(find.text('搜索'));
      await tester.pumpAndSettle();
      
      // Act - 执行搜索
      await tester.enterText(find.byType(TextField), 'flutter');
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();
      
      // Assert
      expect(find.byType(PostCard), findsWidgets);
      expect(find.text('搜索结果'), findsOneWidget);
    });
  });
}
```

#### 1.2 API集成测试
```dart
// API集成测试
class ApiIntegrationTest {
  test('should integrate with real API', () async {
    // Arrange
    final apiService = ApiService();
    
    // Act
    final posts = await apiService.getPosts(page: 1);
    
    // Assert
    expect(posts, isA<List<Post>>());
    expect(posts.isNotEmpty, isTrue);
    
    // 验证数据结构
    for (final post in posts) {
      expect(post.id, isNotEmpty);
      expect(post.title, isNotEmpty);
      expect(post.content, isNotEmpty);
      expect(post.authorId, isNotEmpty);
      expect(post.createdAt, isA<DateTime>());
    }
  });
  
  test('should handle API rate limiting', () async {
    // Arrange
    final apiService = ApiService();
    final futures = <Future>[];
    
    // Act - 发送大量请求
    for (int i = 0; i < 100; i++) {
      futures.add(apiService.getPosts(page: 1));
    }
    
    final results = await Future.wait(futures);
    
    // Assert
    expect(results.length, equals(100));
    // 验证速率限制处理
    final successCount = results.where((r) => r != null).length;
    expect(successCount, greaterThan(50)); // 至少50%成功
  });
}
```

### 2. 数据库集成测试

#### 2.1 数据一致性测试
```dart
// 数据一致性测试
class DataConsistencyTest {
  test('should maintain data consistency across operations', () async {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Test Post',
      content: 'Test Content',
      authorId: 'user1',
      createdAt: DateTime.now(),
    );
    
    // Act - 创建帖子
    await postService.createPost(post);
    
    // Act - 更新帖子
    final updatedPost = post.copyWith(title: 'Updated Title');
    await postService.updatePost(updatedPost);
    
    // Act - 获取帖子
    final retrievedPost = await postService.getPost('1');
    
    // Assert
    expect(retrievedPost.title, equals('Updated Title'));
    expect(retrievedPost.content, equals('Test Content'));
    expect(retrievedPost.authorId, equals('user1'));
  });
  
  test('should handle concurrent data modifications', () async {
    // Arrange
    final post = Post(
      id: '1',
      title: 'Original Title',
      content: 'Original Content',
      authorId: 'user1',
      createdAt: DateTime.now(),
    );
    
    await postService.createPost(post);
    
    // Act - 并发修改
    final futures = <Future>[];
    for (int i = 0; i < 10; i++) {
      futures.add(
        postService.updatePost(
          post.copyWith(title: 'Updated Title $i'),
        ),
      );
    }
    
    await Future.wait(futures);
    
    // Assert - 验证数据完整性
    final finalPost = await postService.getPost('1');
    expect(finalPost.title, startsWith('Updated Title'));
    expect(finalPost.content, equals('Original Content'));
  });
}
```

## 📊 测试覆盖率规则

### 1. 覆盖率要求

#### 1.1 覆盖率目标
```yaml
覆盖率目标:
  单元测试:
    - 代码覆盖率: >80%
    - 分支覆盖率: >75%
    - 函数覆盖率: >90%
    - 行覆盖率: >80%

  Widget测试:
    - 组件覆盖率: >70%
    - 交互覆盖率: >60%
    - 状态覆盖率: >80%
    - 场景覆盖率: >50%

  集成测试:
    - 功能覆盖率: >60%
    - 流程覆盖率: >50%
    - 接口覆盖率: >80%
    - 场景覆盖率: >40%
```

#### 1.2 覆盖率报告
```yaml
报告生成:
  报告类型:
    - HTML报告
    - JSON报告
    - XML报告
    - 控制台报告

  报告内容:
    - 覆盖率统计
    - 未覆盖代码
    - 覆盖率趋势
    - 覆盖率对比

  报告发布:
    - 本地生成
    - CI/CD集成
    - 团队分享
    - 历史记录
```

### 2. 覆盖率分析

#### 2.1 覆盖率分析工具
```dart
// 覆盖率分析
class CoverageAnalysis {
  static void analyzeCoverage() {
    // 分析覆盖率报告
    final coverageReport = CoverageReporter.getReport();
    
    // 识别低覆盖率模块
    final lowCoverageModules = coverageReport.modules
        .where((module) => module.coverage < 80)
        .toList();
    
    // 生成改进建议
    for (final module in lowCoverageModules) {
      _generateImprovementSuggestions(module);
    }
  }
  
  static void _generateImprovementSuggestions(CoverageModule module) {
    print('模块 ${module.name} 覆盖率不足:');
    print('- 当前覆盖率: ${module.coverage}%');
    print('- 建议增加测试用例');
    print('- 重点关注未覆盖的分支');
  }
}
```

## 📋 测试数据管理

### 1. 测试数据规范

#### 1.1 测试数据分类
```yaml
数据分类:
  用户数据:
    - 测试用户账号
    - 用户角色数据
    - 用户权限数据
    - 用户配置数据

  内容数据:
    - 测试帖子
    - 测试评论
    - 测试媒体文件
    - 测试标签数据

  系统数据:
    - 配置数据
    - 元数据
    - 统计数据
    - 日志数据

  边界数据:
    - 空数据
    - 最大值数据
    - 特殊字符数据
    - 异常格式数据
```

#### 1.2 测试数据生成
```dart
// 测试数据生成器
class TestDataGenerator {
  static Post generatePost({
    String? id,
    String? title,
    String? content,
    String? authorId,
  }) {
    return Post(
      id: id ?? _generateId(),
      title: title ?? _generateTitle(),
      content: content ?? _generateContent(),
      authorId: authorId ?? _generateUserId(),
      createdAt: DateTime.now(),
      likes: Random().nextInt(100),
      comments: Random().nextInt(50),
    );
  }
  
  static User generateUser({
    String? id,
    String? name,
    String? email,
  }) {
    return User(
      id: id ?? _generateId(),
      name: name ?? _generateName(),
      email: email ?? _generateEmail(),
      createdAt: DateTime.now(),
    );
  }
  
  static String _generateId() {
    return 'test_${Random().nextInt(10000)}';
  }
  
  static String _generateTitle() {
    final titles = ['Test Post', 'Sample Post', 'Demo Post'];
    return titles[Random().nextInt(titles.length)];
  }
  
  static String _generateContent() {
    return 'This is a test content for testing purposes.';
  }
  
  static String _generateName() {
    return 'Test User ${Random().nextInt(100)}';
  }
  
  static String _generateEmail() {
    return 'test${Random().nextInt(100)}@example.com';
  }
}
```

## ✅ 测试验收标准

### 1. 测试质量验收

#### 1.1 测试完整性验收
```yaml
验收标准:
  测试覆盖:
    - 单元测试覆盖率>80%
    - Widget测试覆盖率>70%
    - 集成测试覆盖率>60%
    - 功能测试覆盖率>90%

  测试质量:
    - 测试用例通过率100%
    - 测试用例可重复执行
    - 测试用例独立性强
    - 测试用例维护性好

  测试效率:
    - 单元测试执行时间<5分钟
    - Widget测试执行时间<10分钟
    - 集成测试执行时间<30分钟
    - 全量测试执行时间<60分钟
```

#### 1.2 测试结果验收
```yaml
验收标准:
  功能测试:
    - 所有功能测试通过
    - 边界条件测试通过
    - 异常情况测试通过
    - 用户场景测试通过

  性能测试:
    - 响应时间达标
    - 内存使用合理
    - CPU使用正常
    - 网络请求优化

  安全测试:
    - 安全漏洞0个
    - 输入验证100%
    - 权限控制正确
    - 数据保护到位
```

### 2. 测试流程验收

#### 2.1 测试流程标准
```yaml
流程标准:
  测试执行:
    - 自动化测试比例>80%
    - 测试执行频率>95%
    - 测试结果反馈及时
    - 测试问题跟踪完整

  测试维护:
    - 测试用例更新及时
    - 测试数据管理规范
    - 测试环境稳定
    - 测试工具维护良好

  团队协作:
    - 测试规范执行100%
    - 测试知识共享充分
    - 测试技能提升持续
    - 测试文化建立良好
```

---

**创建时间**: 2024年12月19日  
**版本**: v1.0  
**测试负责人**: 测试工程师  
**技术负责人**: 技术负责人  
**下次评审**: 2025年1月19日
