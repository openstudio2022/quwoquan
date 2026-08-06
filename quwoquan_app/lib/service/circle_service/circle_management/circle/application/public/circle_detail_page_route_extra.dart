import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;

enum CircleDetailSourceAppearance { inherit, light, dark }

class CircleDetailPageRouteExtra {
  const CircleDetailPageRouteExtra({
    this.referralSource,
    this.sourceAppearanceMode = CircleDetailSourceAppearance.inherit,
  });

  final ReferralSource? referralSource;
  final CircleDetailSourceAppearance sourceAppearanceMode;
}
