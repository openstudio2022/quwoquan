import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/features/home/models/user_models.dart';

/// 主题相关的便捷Provider
final isDarkProvider = Provider<bool>((ref) {
  return ref.watch(themeProvider).isDark;
});

/// 用户数据Provider
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(String username) async {
    // Stub implementation
    state = User(
      id: username,
      username: username,
    );
  }
}

final userDataProvider = NotifierProvider<UserDataNotifier, User?>(() {
  return UserDataNotifier();
});

/// 响应式Provider (stub)
final responsiveProvider = Provider<Map<String, dynamic>>((ref) {
  return {};
});

/// 数据服务Provider
final dataServiceProvider = Provider<DataService>((ref) {
  return DataServiceImpl();
});

