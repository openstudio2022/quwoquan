import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/citation_destination_resolver.dart';
import 'package:quwoquan_app/runtime/di/navigation/citation_destination_navigation_mapper.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/application/public/search_feedback_fact_appender.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_route_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/media/content_preview_card.dart';
import 'package:quwoquan_app/design_system/content/post_preview_list_tile.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_execution_values.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/post_search_item_view.dart';
import 'package:quwoquan_app/runtime/shell/loading/app_request_wait_controller.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_result_tab_spec.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/location_place_landing_page.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_media_wiring.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

part 'search_network_results_page_card_widgets.dart';
part 'search_network_results_page_models.dart';
part 'search_network_results_page_state.dart';
part 'search_network_results_page_state_data_navigation.dart';
part 'search_network_results_page_state_helpers.dart';
part 'search_network_results_page_state_loading.dart';
part 'search_network_results_page_state_view_helpers.dart';
part 'search_network_results_page_status_widgets.dart';

class _SearchResultTokens {
  _SearchResultTokens._();

  static const double sectionTitleSize = AppTypography.iosBody;
  static const FontWeight sectionTitleWeight = AppTypography.semiBold;
  static const double bodySize = AppTypography.iosCallout;
  static const FontWeight bodyWeight = AppTypography.regular;
  static const double cardTitleSize = AppTypography.iosFootnote;
  static const double captionSize = AppTypography.iosCaption1;
}

class SearchNetworkResultsPage extends ConsumerStatefulWidget {
  const SearchNetworkResultsPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<SearchNetworkResultsPage> createState() =>
      _SearchNetworkResultsPageState();
}
