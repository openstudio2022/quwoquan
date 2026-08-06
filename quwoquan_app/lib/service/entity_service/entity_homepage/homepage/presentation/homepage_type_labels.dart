import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// Homepage wire type → 用户可见标签的唯一 UI 映射。
///
/// wire 值仍由契约 DTO 承载；页面不得再维护私有 label map。
String homepageTypeLabel(String type) {
  return switch (type.trim()) {
    'hotel' => CreationText.homepageTypeHotel,
    'restaurant' => CreationText.homepageTypeRestaurant,
    'vehicle' => CreationText.homepageTypeVehicle,
    'sight' => CreationText.homepageTypeSight,
    'university' => CreationText.homepageTypeUniversity,
    'school' => CreationText.homepageTypeSchool,
    'travel_photo' => CreationText.homepageTypeTravelPhoto,
    'museum' => CreationText.homepageTypeMuseum,
    'heritage_site' => CreationText.homepageTypeHeritageSite,
    'ancient_town' => CreationText.homepageTypeAncientTown,
    'religious_site' => CreationText.homepageTypeReligiousSite,
    'check_in_spot' => CreationText.homepageTypeCheckInSpot,
    'natural_landscape' => CreationText.homepageTypeNaturalLandscape,
    'park' => CreationText.homepageTypePark,
    'hot_spring' => CreationText.homepageTypeHotSpring,
    'theme_park' => CreationText.homepageTypeThemePark,
    'transport_hub' => CreationText.homepageTypeTransportHub,
    'city' => CreationText.homepageTypeCity,
    'route' => CreationText.homepageTypeRoute,
    'photo_spot' => CreationText.homepageTypePhotoSpot,
    'gear' => CreationText.homepageTypeGear,
    'poi' || 'place' => CreationText.homepageTypePoi,
    'author' => CreationText.homepageTypeAuthor,
    'circle' => CreationText.homepageTypeCircle,
    _ => ObjectHomepageText.homepageTypeDefault,
  };
}

/// Homepage lifecycle wire status → 用户可见标签的唯一 UI 映射。
String homepageStatusLabel(String? status) {
  return switch ((status ?? '').trim()) {
    'candidate' || 'pending_verify' => CreationText.homepageStatusCandidate,
    'offline' => CreationText.homepageStatusOffline,
    'published' => CreationText.homepageStatusPublished,
    _ => CreationText.homepageStatusUnknown,
  };
}
