import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;

class ArticleDetailPageRouteExtra {
  const ArticleDetailPageRouteExtra({
    this.referralSource,
    this.feedRequestId,
    this.position,
  });

  final ReferralSource? referralSource;
  final String? feedRequestId;

  /// 入口文章在 feed 中的位置（推荐归因；从 feed 列表序号透传）。
  final int? position;
}

class CircleDetailPageRouteExtra {
  const CircleDetailPageRouteExtra({
    this.referralSource,
  });

  final ReferralSource? referralSource;
}

class OtherProfilePageRouteExtra {
  const OtherProfilePageRouteExtra({
    this.referralSource,
    this.subAccountId,
    this.avatar,
    this.displayName,
    this.backgroundImage,
  });

  final ReferralSource? referralSource;
  final String? subAccountId;
  final String? avatar;
  final String? displayName;
  final String? backgroundImage;
}
