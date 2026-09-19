// Code generated from contracts/metadata/_shared/types.yaml. DO NOT EDIT.
import 'dart:convert';

import 'package:crypto/crypto.dart';

import "package:quwoquan_cloud_contracts/src/generated/shared_operation_types.g.dart";

const compiledContentPresentationCollections = <String, List<String>>{
  "contentTypes": <String>["article", "image", "video"],
  "listObjectKinds": <String>["entity_homepage", "post"],
  "openSurfaces": <String>[
    "article_reader",
    "home_feed",
    "homepage_detail",
    "media_immersive",
    "profile_works",
  ],
  "presentationRecipes": <String>[
    "article_excerpt_card",
    "cover_media_card",
    "homepage_summary_card",
  ],
};
const compiledContentPresentationContractDigest =
    "sha256:8ef3b67169b934c19c9ac825b73085c4aa0cdb809ef82429b4b1e1e2d0bfca05";
final compiledContentPresentationContract = ClientContentPresentationContract(
  contentTypes: const <ContentType>[
    ContentType.article,
    ContentType.image,
    ContentType.video,
  ],
  listObjectKinds: const <ListObjectKind>[
    ListObjectKind.entityHomepage,
    ListObjectKind.post,
  ],
  openSurfaces: const <ContentUiSurface>[
    ContentUiSurface.articleReader,
    ContentUiSurface.homeFeed,
    ContentUiSurface.homepageDetail,
    ContentUiSurface.mediaImmersive,
    ContentUiSurface.profileWorks,
  ],
  presentationRecipes: const <FeedPresentationRecipe>[
    FeedPresentationRecipe.articleExcerptCard,
    FeedPresentationRecipe.coverMediaCard,
    FeedPresentationRecipe.homepageSummaryCard,
  ],
  contractDigest: compiledContentPresentationContractDigest,
);

const missingDeclarationContentPresentationCollections = <String, List<String>>{
  "contentTypes": <String>["article", "image", "video"],
  "listObjectKinds": <String>["post"],
  "openSurfaces": <String>["article_reader", "media_immersive"],
  "presentationRecipes": <String>["article_excerpt_card", "cover_media_card"],
};
const missingDeclarationContentPresentationContractDigest =
    "sha256:cf070afb148dc07d723c9eb76ec9e87fafcffcd16c07ad6a22f367d393de9281";
final missingDeclarationContentPresentationContract =
    ClientContentPresentationContract(
      contentTypes: const <ContentType>[
        ContentType.article,
        ContentType.image,
        ContentType.video,
      ],
      listObjectKinds: const <ListObjectKind>[ListObjectKind.post],
      openSurfaces: const <ContentUiSurface>[
        ContentUiSurface.articleReader,
        ContentUiSurface.mediaImmersive,
      ],
      presentationRecipes: const <FeedPresentationRecipe>[
        FeedPresentationRecipe.articleExcerptCard,
        FeedPresentationRecipe.coverMediaCard,
      ],
      contractDigest: missingDeclarationContentPresentationContractDigest,
    );

const _maxItems = <String, int>{
  "contentTypes": 32,
  "listObjectKinds": 32,
  "openSurfaces": 32,
  "presentationRecipes": 32,
};

int _compareUtf8(String left, String right) {
  final a = utf8.encode(left);
  final b = utf8.encode(right);
  for (var i = 0; i < a.length && i < b.length; i++) {
    if (a[i] != b[i]) return a[i].compareTo(b[i]);
  }
  return a.length.compareTo(b.length);
}

String canonicalClientContentPresentationContract(
  ClientContentPresentationContract value,
) => canonicalClientContentPresentationCollections(value.toWire());

String canonicalClientContentPresentationCollections(
  Map<String, Object?> value,
) {
  final fields = compiledContentPresentationCollections.keys.toSet();
  if (!value.keys.every(
        (key) => fields.contains(key) || key == 'contractDigest',
      ) ||
      !fields.every(value.containsKey)) {
    throw const FormatException('Expected exactly four capability collections');
  }
  final normalized = <String, List<String>>{};
  for (final entry in compiledContentPresentationCollections.entries) {
    final values = value[entry.key];
    if (values is! List || values.length > _maxItems[entry.key]!) {
      throw const FormatException('Expected bounded non-null capability array');
    }
    final seen = <String>{};
    for (final member in values) {
      if (member is! String ||
          !entry.value.contains(member) ||
          !seen.add(member)) {
        throw const FormatException('Invalid or duplicate capability member');
      }
    }
    normalized[entry.key] = seen.toList()..sort(_compareUtf8);
  }
  return jsonEncode(normalized);
}

String digestClientContentPresentationContract(
  ClientContentPresentationContract value,
) =>
    'sha256:${sha256.convert(utf8.encode(canonicalClientContentPresentationContract(value)))}';

void validateClientContentPresentationContract(
  ClientContentPresentationContract value,
) {
  // 摘要只表示能力集合身份；不是授权。
  if (value.contractDigest != digestClientContentPresentationContract(value)) {
    throw const FormatException('Client presentation contract digest mismatch');
  }
}
