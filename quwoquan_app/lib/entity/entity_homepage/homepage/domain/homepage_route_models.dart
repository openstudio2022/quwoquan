import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_view_data.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_tab.dart';

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
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
    this.feedRequestId = '',
    this.recommendationTraceId = '',
    this.experimentBucket = '',
    this.rolloutCohort = '',
    this.initialTabTarget,
  });

  final bool selectionMode;
  final HomepageSummary? initialSummary;
  final ReferralSource? referralSource;
  final UiErrorAppearanceMode sourceAppearanceMode;
  final String feedRequestId;
  final String recommendationTraceId;
  final String experimentBucket;
  final String rolloutCohort;
  final HomepageDetailTabTarget? initialTabTarget;
}
