import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_preview_card.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// TA 主页「我与TA的交集」预览卡。
///
/// 视觉与我的主页交集入口同源：委托共享 [ObjectIntersectionPreviewCard]（objectType=user）。
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
    return ObjectIntersectionPreviewCard(
      objectId: userId,
      objectType: 'user',
      title: UITextConstants.profileWhyRecommendTitle,
      emptyText: UITextConstants.profileIntersectionEmptyOther,
      referralSource: ReferralSource.authorProfile,
      cardKey: cardKey,
      emptyKey: emptyKey,
    );
  }
}
