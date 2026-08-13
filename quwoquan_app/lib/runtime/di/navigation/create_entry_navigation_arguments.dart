import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';

/// Cross-object navigation payload for the canonical create-entry route.
///
/// This type belongs to the navigation composition boundary because it joins
/// Homepage, Circle and Gathering context before the Post presentation is
/// constructed.
final class CreateEntryArguments {
  const CreateEntryArguments({
    this.homepage,
    this.circleId,
    this.circleName,
    this.gatheringId,
    this.gatheringTitle,
  });

  final HomepageCanonicalReference? homepage;
  final String? circleId;
  final String? circleName;

  /// 从行动入口进入创作时携带的 canonical Gathering ID（发布回顾）。
  /// 只是创作上下文预填；作者可在创作页移除关联，最终是否写入由
  /// PublishSettings.gatheringRef 决定，服务端仍校验 Participation。
  final String? gatheringId;
  final String? gatheringTitle;
}
