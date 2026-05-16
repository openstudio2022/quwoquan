import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;

class HomepagePickerPageRouteExtra {
  const HomepagePickerPageRouteExtra({this.initialSelection});

  final HomepageCanonicalReference? initialSelection;
}

class HomepagePickerSelectionResult {
  const HomepagePickerSelectionResult._({
    this.selection,
    required this.clearSelection,
  });

  const HomepagePickerSelectionResult.selected(
    HomepageCanonicalReference selection,
  ) : this._(selection: selection, clearSelection: false);

  const HomepagePickerSelectionResult.clear()
    : this._(selection: null, clearSelection: true);

  final HomepageCanonicalReference? selection;
  final bool clearSelection;
}

class HomepageDetailPageRouteExtra {
  const HomepageDetailPageRouteExtra({
    this.selectionMode = false,
    this.initialSummary,
    this.referralSource,
  });

  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final ReferralSource? referralSource;
}
