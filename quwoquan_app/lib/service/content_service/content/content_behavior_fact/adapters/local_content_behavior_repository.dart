import 'dart:developer' as developer;

import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';

/// 离线浏览只保留本机聚合诊断，不保存事件正文、不创建云端 outbox。
final class LocalContentBehaviorRepository extends BehaviorRepository {
  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (events.isEmpty) return;
    developer.log(
      'source=bundled_snapshot localEventCount=${events.length} remoteAccepted=false',
      name: 'ContentBehavior',
    );
  }

  @override
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    throw contentCapabilityUnavailable('onboarding_interest');
  }

  @override
  Future<void> clearPendingForLogout() async {
    // 本地聚合诊断没有持久队列，也没有可以补传的云端事实。
  }
}
