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
