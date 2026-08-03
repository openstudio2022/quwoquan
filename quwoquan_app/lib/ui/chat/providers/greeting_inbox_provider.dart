import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 消息首页的待处理打招呼摘要；完整收/发历史由 GreetingInboxPage 自行加载。
final chatGreetingInboxProvider = FutureProvider.autoDispose
    .family<List<GreetingRequestViewData>, int>((ref, limit) async {
      return ref
          .read(greetingRepositoryProvider)
          .listInbox(status: 'pending', limit: limit);
    });
