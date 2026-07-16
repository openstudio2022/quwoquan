import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// TA 主页「我与TA的交集」预览卡。
///
/// 视觉与我的主页交集入口同源：直接消费 [ObjectIntersectionSection]（objectType=user）。
/// 无交集时不再整块消失，而是展示克制空态，避免主页 IA 断层。
class OtherProfileIntersectionCard extends ConsumerWidget {
  const OtherProfileIntersectionCard({super.key, required this.userId});

  static const Key cardKey = ValueKey<String>(
    'other-profile-intersection-card',
  );
  static const Key emptyKey = ValueKey<String>(
    'other-profile-intersection-empty',
  );

  final String userId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final query = ObjectIntersectionQuery(
      objectAId: ref.watch(currentUserIdProvider),
      objectAType: 'user',
      objectBId: userId,
      objectBType: 'user',
    );
    if (!query.isResolvable) {
      return const SizedBox.shrink();
    }
    return ObjectIntersectionSection(
      key: cardKey,
      query: query,
      title: UITextConstants.profileWhyRecommendTitle,
      isDark: CupertinoTheme.of(context).brightness == Brightness.dark,
      emptyText: UITextConstants.profileIntersectionEmptyOther,
      emptyKey: emptyKey,
    );
  }
}
