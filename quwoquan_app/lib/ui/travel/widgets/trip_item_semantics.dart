import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

String tripItemKindLabel(TripPlanItemKind kind) => switch (kind) {
  TripPlanItemKind.stay => TravelText.itemStay,
  TripPlanItemKind.food => TravelText.itemFood,
  TripPlanItemKind.sight => TravelText.itemSight,
  TripPlanItemKind.activity => TravelText.itemActivity,
  TripPlanItemKind.transport => TravelText.itemTransport,
  TripPlanItemKind.rest => TravelText.itemRest,
  TripPlanItemKind.freeTime => TravelText.itemFreeTime,
};

IconData tripItemKindIcon(TripPlanItemKind kind) => switch (kind) {
  TripPlanItemKind.stay => CupertinoIcons.bed_double,
  TripPlanItemKind.food => CupertinoIcons.house_alt,
  TripPlanItemKind.sight => CupertinoIcons.compass,
  TripPlanItemKind.activity => CupertinoIcons.person_2,
  TripPlanItemKind.transport => CupertinoIcons.car_detailed,
  TripPlanItemKind.rest => CupertinoIcons.moon,
  TripPlanItemKind.freeTime => CupertinoIcons.time,
};

String tripStatusLabel(TripPlanStatus status) => switch (status) {
  TripPlanStatus.planning => TravelText.statusPlanning,
  TripPlanStatus.active => TravelText.statusActive,
  TripPlanStatus.completed => TravelText.statusCompleted,
  TripPlanStatus.archived => TravelText.statusArchived,
};

String tripStatusActionLabel(TripPlanStatus status) => switch (status) {
  TripPlanStatus.planning => TravelText.startTrip,
  TripPlanStatus.active => TravelText.completeTrip,
  TripPlanStatus.completed => TravelText.reopenTrip,
  TripPlanStatus.archived => TravelText.restoreTrip,
};
