import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';

/// Cross-object navigation payload for the canonical create-entry route.
///
/// This type belongs to the navigation composition boundary because it joins
/// Homepage and Circle context before the Post presentation is constructed.
final class CreateEntryArguments {
  const CreateEntryArguments({this.homepage, this.circleId, this.circleName});

  final HomepageCanonicalReference? homepage;
  final String? circleId;
  final String? circleName;
}
