import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 主页影响力摘要数据源（「TA的影响 / 我的影响力」共用，按 userId 维度缓存）。
///
/// 失败时由消费方按 async 三态收起模块（不造假、不放占位数字）。
final authorImpactProvider = FutureProvider.autoDispose
    .family<AuthorImpactSummary, String>((ref, userId) {
      return ref.watch(userProfileRepositoryProvider).getAuthorImpact(userId);
    });
