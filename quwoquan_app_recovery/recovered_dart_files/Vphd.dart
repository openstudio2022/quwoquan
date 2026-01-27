import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'user_api_service.dart';
import 'user_mock_service.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';

/// 用户服务提供者
/// 根据配置返回API或Mock实现
final userServiceProvider = Provider<UserApiService>((ref) {
  final dataService = ref.watch(dataServiceProvider);
  return UserApiService(dataService);
});

/// Mock用户服务提供者
final userMockServiceProvider = Provider<UserMockService>((ref) {
  return UserMockService();
});

/// 用户数据Provider
final userDataProvider = StateNotifierProvider<UserDataNotifier, AsyncValue<User?>>((ref) {
  final userService = ref.watch(userServiceProvider);
  return UserDataNotifier(userService);
});

/// 用户数据Notifier
class UserDataNotifier extends StateNotifier<AsyncValue<User?>> {
  final UserApiService _userService;

  UserDataNotifier(this._userService) : super(const AsyncValue.loading());

  /// 加载用户数据
  Future<void> loadUser(String username) async {
    state = const AsyncValue.loading();
    
    try {
      final user = await _userService.getUserByUsername(username);
      if (user != null) {
        state = AsyncValue.data(user);
      } else {
        state = AsyncValue.error('用户不存在', StackTrace.current);
      }
    } catch (error, stackTrace) {
      state = AsyncValue.error(error, stackTrace);
    }
  }

  /// 关注用户
  Future<void> followUser(String userId) async {
    try {
      await _userService.followUser(userId);
      // 更新本地状态
      state.whenData((user) {
        if (user != null) {
          final updatedUser = user.copyWith(
            isFollowing: true,
            followers: user.followers + 1,
          );
          state = AsyncValue.data(updatedUser);
        }
      });
    } catch (error, stackTrace) {
      state = AsyncValue.error(error, stackTrace);
    }
  }

  /// 取消关注用户
  Future<void> unfollowUser(String userId) async {
    try {
      await _userService.unfollowUser(userId);
      // 更新本地状态
      state.whenData((user) {
        if (user != null) {
          final updatedUser = user.copyWith(
            isFollowing: false,
            followers: user.followers - 1,
          );
          state = AsyncValue.data(updatedUser);
        }
      });
    } catch (error, stackTrace) {
      state = AsyncValue.error(error, stackTrace);
    }
  }
}
