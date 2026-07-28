import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

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
    'travel_photo' => CreationText.homepageTypeTravelPhoto,
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
