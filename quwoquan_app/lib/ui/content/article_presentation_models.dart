import 'package:flutter/foundation.dart';

enum ArticleTemplatePreset { gentle, ritual, diffuse, journal, tech }

extension ArticleTemplatePresetX on ArticleTemplatePreset {
  String get label => switch (this) {
    ArticleTemplatePreset.gentle => '柔和',
    ArticleTemplatePreset.ritual => '礼记',
    ArticleTemplatePreset.diffuse => '弥散',
    ArticleTemplatePreset.journal => '手帐',
    ArticleTemplatePreset.tech => '科技',
  };
}

ArticleTemplatePreset articleTemplatePresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'ritual' => ArticleTemplatePreset.ritual,
    'diffuse' => ArticleTemplatePreset.diffuse,
    'journal' => ArticleTemplatePreset.journal,
    'tech' => ArticleTemplatePreset.tech,
    _ => ArticleTemplatePreset.gentle,
  };
}

enum ArticleFontPreset { clean, classic, handwritten, rounded, mono }

extension ArticleFontPresetX on ArticleFontPreset {
  String get label => switch (this) {
    ArticleFontPreset.clean => '清雅',
    ArticleFontPreset.classic => '经典',
    ArticleFontPreset.handwritten => '手写',
    ArticleFontPreset.rounded => '圆体',
    ArticleFontPreset.mono => '等宽',
  };
}

ArticleFontPreset articleFontPresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'classic' => ArticleFontPreset.classic,
    'handwritten' => ArticleFontPreset.handwritten,
    'rounded' => ArticleFontPreset.rounded,
    'mono' => ArticleFontPreset.mono,
    _ => ArticleFontPreset.clean,
  };
}

@immutable
class ArticlePageData {
  const ArticlePageData({
    required this.id,
    this.title = '',
    this.body = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
  });

  factory ArticlePageData.fromMap(Map<String, dynamic> map) {
    return ArticlePageData(
      id: (map['id'] ?? '').toString(),
      title: (map['title'] ?? '').toString(),
      body: (map['body'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
    );
  }

  final String id;
  final String title;
  final String body;
  final String imageUrl;
  final String imageLayout;
  final String caption;

  bool get hasText => title.trim().isNotEmpty || body.trim().isNotEmpty;
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get isEmpty => !hasText && !hasImage;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticlePageData copyWith({
    String? id,
    String? title,
    String? body,
    String? imageUrl,
    String? imageLayout,
    String? caption,
  }) {
    return ArticlePageData(
      id: id ?? this.id,
      title: title ?? this.title,
      body: body ?? this.body,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'title': title,
      'body': body,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
    };
  }
}
