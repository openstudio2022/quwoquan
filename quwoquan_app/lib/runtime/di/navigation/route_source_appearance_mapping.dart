import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_route_models.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_appearance.dart';

UiErrorAppearanceMode uiErrorAppearanceModeFromCircleRoute(
  CircleDetailSourceAppearance mode,
) {
  return switch (mode) {
    CircleDetailSourceAppearance.inherit => UiErrorAppearanceMode.inherit,
    CircleDetailSourceAppearance.light => UiErrorAppearanceMode.light,
    CircleDetailSourceAppearance.dark => UiErrorAppearanceMode.dark,
  };
}

UiErrorAppearanceMode uiErrorAppearanceModeFromHomepageRoute(
  HomepageDetailSourceAppearance mode,
) {
  return switch (mode) {
    HomepageDetailSourceAppearance.inherit => UiErrorAppearanceMode.inherit,
    HomepageDetailSourceAppearance.light => UiErrorAppearanceMode.light,
    HomepageDetailSourceAppearance.dark => UiErrorAppearanceMode.dark,
  };
}
