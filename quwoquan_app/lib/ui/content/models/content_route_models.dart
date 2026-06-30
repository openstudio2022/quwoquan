import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';

class CircleDetailPageRouteExtra {
  const CircleDetailPageRouteExtra({
    this.referralSource,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  });

  final ReferralSource? referralSource;
  final UiErrorAppearanceMode sourceAppearanceMode;
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
