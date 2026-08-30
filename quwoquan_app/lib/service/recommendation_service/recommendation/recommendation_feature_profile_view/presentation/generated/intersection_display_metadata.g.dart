// Code generated from the canonical intersection registry. DO NOT EDIT.
// Source: recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show IntersectionDimension, IntersectionObjectKind;

final class IntersectionKindDisplayMetadata {
  const IntersectionKindDisplayMetadata({required this.iconKey});

  final String iconKey;

  static IntersectionKindDisplayMetadata? of(String? kind) {
    if (kind == null) return null;
    return intersectionKindDisplayMetadata[kind.trim()];
  }
}

const Map<String, IntersectionKindDisplayMetadata>
intersectionKindDisplayMetadata = <String, IntersectionKindDisplayMetadata>{
  "coCommented": IntersectionKindDisplayMetadata(iconKey: "discussion"),
  "coExperiencedGathering": IntersectionKindDisplayMetadata(
    iconKey: "experience",
  ),
  "coLiked": IntersectionKindDisplayMetadata(iconKey: "like"),
  "coSharedContent": IntersectionKindDisplayMetadata(iconKey: "share"),
  "coVisitedEntity": IntersectionKindDisplayMetadata(iconKey: "place"),
  "coWishlistedEntity": IntersectionKindDisplayMetadata(iconKey: "place"),
  "commonFollower": IntersectionKindDisplayMetadata(iconKey: "people"),
  "followeeDiscussedThis": IntersectionKindDisplayMetadata(
    iconKey: "discussion",
  ),
  "followeeInObject": IntersectionKindDisplayMetadata(iconKey: "followHere"),
  "followeeViewedObject": IntersectionKindDisplayMetadata(iconKey: "viewing"),
  "followeeViewing": IntersectionKindDisplayMetadata(iconKey: "viewing"),
  "followeeVisited": IntersectionKindDisplayMetadata(iconKey: "placeHere"),
  "sameIndustry": IntersectionKindDisplayMetadata(iconKey: "work"),
  "sharedCircle": IntersectionKindDisplayMetadata(iconKey: "circle"),
  "sharedEntityAttention": IntersectionKindDisplayMetadata(
    iconKey: "attention",
  ),
  "sharedFollowees": IntersectionKindDisplayMetadata(iconKey: "people"),
  "sharedTagSample": IntersectionKindDisplayMetadata(iconKey: "interest"),
};

const Map<String, String> intersectionVisualToneByIconKey = <String, String>{
  'alumni': 'mist',
  'attention': 'stone',
  'circle': 'sage',
  'discussion': 'clay',
  'experience': 'sage',
  'followHere': 'sage',
  'interest': 'stone',
  'like': 'clay',
  'people': 'sage',
  'place': 'tea',
  'placeHere': 'tea',
  'share': 'clay',
  'viewing': 'sage',
  'work': 'mist',
};

const Map<IntersectionDimension, String>
intersectionFallbackIconKeyByDimension = <IntersectionDimension, String>{
  IntersectionDimension.identity: "alumni",
  IntersectionDimension.location: "place",
  IntersectionDimension.content: "discussion",
  IntersectionDimension.interest: "interest",
  IntersectionDimension.relationship: "people",
};

const Map<IntersectionObjectKind, String> intersectionAssetKindByObjectKind =
    <IntersectionObjectKind, String>{
      IntersectionObjectKind.person: "avatar",
      IntersectionObjectKind.circle: "circleAvatar",
      IntersectionObjectKind.school: "emblem",
      IntersectionObjectKind.place: "coverImage",
      IntersectionObjectKind.enterprise: "logo",
      IntersectionObjectKind.route: "coverImage",
      IntersectionObjectKind.photoSpot: "coverImage",
      IntersectionObjectKind.gear: "coverImage",
      IntersectionObjectKind.content: "coverImage",
      IntersectionObjectKind.gathering: "coverImage",
    };
