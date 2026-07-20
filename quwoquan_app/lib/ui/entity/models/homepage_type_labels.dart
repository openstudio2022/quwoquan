import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// Homepage wire type → 用户可见标签的唯一 UI 映射。
///
/// wire 值仍由契约 DTO 承载；页面不得再维护私有 label map。
String homepageTypeLabel(String type) {
  return switch (type.trim()) {
    'hotel' => UITextConstants.homepageTypeHotel,
    'restaurant' => UITextConstants.homepageTypeRestaurant,
    'vehicle' => UITextConstants.homepageTypeVehicle,
    'sight' => UITextConstants.homepageTypeSight,
    'university' => UITextConstants.homepageTypeUniversity,
    'travel_photo' => UITextConstants.homepageTypeTravelPhoto,
    'poi' || 'place' => UITextConstants.homepageTypePoi,
    'author' => UITextConstants.homepageTypeAuthor,
    'circle' => UITextConstants.homepageTypeCircle,
    _ => UITextConstants.homepageTypeDefault,
  };
}

/// Homepage lifecycle wire status → 用户可见标签的唯一 UI 映射。
String homepageStatusLabel(String? status) {
  return switch ((status ?? '').trim()) {
    'candidate' || 'pending_verify' => UITextConstants.homepageStatusCandidate,
    'offline' => UITextConstants.homepageStatusOffline,
    'published' => UITextConstants.homepageStatusPublished,
    _ => UITextConstants.homepageStatusUnknown,
  };
}
