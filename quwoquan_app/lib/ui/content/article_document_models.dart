import 'package:flutter/foundation.dart';

enum ArticleDocumentBlockType {
  paragraph,
  heading2,
  heading3,
  sectionTitle,
  orderedItem,
  bulletItem,
  image,
}

@immutable
class ArticleDocumentBlock {
  const ArticleDocumentBlock({
    required this.id,
    required this.type,
    this.offset = 0,
    this.text = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
    this.orderedIndex,
  });

  factory ArticleDocumentBlock.fromMap(Map<String, dynamic> map) {
    final typeName = (map['type'] ?? 'paragraph').toString().trim();
    final type = switch (typeName) {
      'heading2' => ArticleDocumentBlockType.heading2,
      'heading3' => ArticleDocumentBlockType.heading3,
      'sectionTitle' => ArticleDocumentBlockType.sectionTitle,
      'orderedItem' => ArticleDocumentBlockType.orderedItem,
      'bulletItem' => ArticleDocumentBlockType.bulletItem,
      'image' => ArticleDocumentBlockType.image,
      _ => ArticleDocumentBlockType.paragraph,
    };
    return ArticleDocumentBlock(
      id: (map['id'] ?? '').toString(),
      type: type,
      offset: (map['offset'] as num?)?.toInt() ?? 0,
      text: (map['text'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
      orderedIndex: (map['orderedIndex'] as num?)?.toInt(),
    );
  }

  final String id;
  final ArticleDocumentBlockType type;
  final int offset;
  final String text;
  final String imageUrl;
  final String imageLayout;
  final String caption;
  final int? orderedIndex;

  bool get isTextLike => type != ArticleDocumentBlockType.image;
  bool get hasText => text.trim().isNotEmpty;
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticleDocumentBlock copyWith({
    String? id,
    ArticleDocumentBlockType? type,
    int? offset,
    String? text,
    String? imageUrl,
    String? imageLayout,
    String? caption,
    int? orderedIndex,
  }) {
    return ArticleDocumentBlock(
      id: id ?? this.id,
      type: type ?? this.type,
      offset: offset ?? this.offset,
      text: text ?? this.text,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
      orderedIndex: orderedIndex ?? this.orderedIndex,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      'offset': offset,
      'text': text,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
      if (orderedIndex != null) 'orderedIndex': orderedIndex,
    };
  }
}

@immutable
class ArticleDocumentAsset {
  const ArticleDocumentAsset({
    required this.id,
    required this.offset,
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
  });

  factory ArticleDocumentAsset.fromMap(Map<String, dynamic> map) {
    return ArticleDocumentAsset(
      id: (map['id'] ?? '').toString(),
      offset: (map['offset'] as num?)?.toInt() ?? 0,
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
    );
  }

  final String id;
  final int offset;
  final String imageUrl;
  final String imageLayout;
  final String caption;

  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticleDocumentAsset copyWith({
    String? id,
    int? offset,
    String? imageUrl,
    String? imageLayout,
    String? caption,
  }) {
    return ArticleDocumentAsset(
      id: id ?? this.id,
      offset: offset ?? this.offset,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'offset': offset,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
    };
  }
}

@immutable
class ArticleDocumentData {
  const ArticleDocumentData({
    this.title = '',
    this.body = '',
    this.assets = const <ArticleDocumentAsset>[],
    this.blocks = const <ArticleDocumentBlock>[],
  });

  factory ArticleDocumentData.fromMap(Map<String, dynamic> map) {
    final assets = ((map['assets'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleDocumentAsset.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where((asset) => asset.id.trim().isNotEmpty && asset.hasImage)
        .toList(growable: false);
    final blocks = ((map['blocks'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleDocumentBlock.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where(
          (block) =>
              block.id.trim().isNotEmpty &&
              (block.hasImage || block.hasText || block.isTextLike),
        )
        .toList(growable: false);
    return ArticleDocumentData(
      title: (map['title'] ?? '').toString(),
      body: (map['body'] ?? '').toString(),
      assets: assets,
      blocks: blocks,
    );
  }

  final String title;
  final String body;
  final List<ArticleDocumentAsset> assets;
  final List<ArticleDocumentBlock> blocks;

  bool get hasTitle => title.trim().isNotEmpty;
  bool get hasBody =>
      body.trim().isNotEmpty ||
      blocks.any((block) => block.isTextLike && block.hasText);
  bool get hasAssets => assets.any((asset) => asset.hasImage);
  bool get hasBlocks => blocks.isNotEmpty;
  bool get hasStructuredTextBlocks => blocks.any(
    (block) =>
        block.type == ArticleDocumentBlockType.heading2 ||
        block.type == ArticleDocumentBlockType.heading3 ||
        block.type == ArticleDocumentBlockType.sectionTitle,
  );
  bool get isEmpty => !hasTitle && !hasBody && !hasAssets && !hasBlocks;

  ArticleDocumentData copyWith({
    String? title,
    String? body,
    List<ArticleDocumentAsset>? assets,
    List<ArticleDocumentBlock>? blocks,
  }) {
    return ArticleDocumentData(
      title: title ?? this.title,
      body: body ?? this.body,
      assets: assets ?? this.assets,
      blocks: blocks ?? this.blocks,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'title': title,
      'body': body,
      'assets': assets.map((asset) => asset.toMap()).toList(growable: false),
      'blocks': blocks.map((block) => block.toMap()).toList(growable: false),
    };
  }
}

@immutable
class ArticleTextRange {
  const ArticleTextRange({
    required this.start,
    required this.end,
  });

  final int start;
  final int end;

  bool get isCollapsed => start >= end;

  ArticleTextRange copyWith({
    int? start,
    int? end,
  }) {
    return ArticleTextRange(
      start: start ?? this.start,
      end: end ?? this.end,
    );
  }
}

@immutable
class ArticlePageBinding {
  const ArticlePageBinding({
    this.titleRange,
    this.bodyRange,
    this.assetId,
    this.assetOffset,
    required this.insertOffset,
  });

  final ArticleTextRange? titleRange;
  final ArticleTextRange? bodyRange;
  final String? assetId;
  final int? assetOffset;
  final int insertOffset;

  bool get hasTitleSlice => titleRange != null && !titleRange!.isCollapsed;
  bool get hasBodySlice => bodyRange != null && !bodyRange!.isCollapsed;
  bool get hasAsset => assetId != null && assetId!.trim().isNotEmpty;
}
