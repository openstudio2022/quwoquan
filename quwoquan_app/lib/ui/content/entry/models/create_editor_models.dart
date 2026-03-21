import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

enum EditorStartAction { gallery, write, capture }

enum CreateContentIdentity { moment, work }

extension CreateContentIdentityX on CreateContentIdentity {
  String get value => name;

  String get label => this == CreateContentIdentity.moment ? '点滴' : '作品';
}

@immutable
class IdentitySuggestion {
  const IdentitySuggestion({required this.identity, required this.reason});

  final CreateContentIdentity identity;
  final String reason;
}

enum CreateEditorKind { media, text }

enum CreateMediaKind { none, images, video }

enum TitlePresentation { collapsed, expanded }

enum CreateTextBlockType { paragraph, orderedItem, image }

enum CreateTextImageLayout { fullWidth, wrapLeft, wrapRight }

@immutable
class CreateTextBlock {
  const CreateTextBlock({
    required this.id,
    required this.type,
    this.text = '',
    this.imagePath = '',
    this.imageLayout = CreateTextImageLayout.fullWidth,
  });

  factory CreateTextBlock.paragraph({
    required String id,
    String text = '',
  }) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.paragraph,
      text: text,
    );
  }

  factory CreateTextBlock.orderedItem({
    required String id,
    String text = '',
  }) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.orderedItem,
      text: text,
    );
  }

  factory CreateTextBlock.image({
    required String id,
    required String imagePath,
    CreateTextImageLayout imageLayout = CreateTextImageLayout.fullWidth,
  }) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.image,
      imagePath: imagePath,
      imageLayout: imageLayout,
    );
  }

  factory CreateTextBlock.fromMap(Map<String, dynamic> map) {
    final typeName = (map['type'] ?? 'paragraph').toString().trim();
    final type = switch (typeName) {
      'orderedItem' => CreateTextBlockType.orderedItem,
      'image' => CreateTextBlockType.image,
      _ => CreateTextBlockType.paragraph,
    };
    final layoutName = (map['imageLayout'] ?? 'fullWidth').toString().trim();
    final imageLayout = switch (layoutName) {
      'wrapLeft' => CreateTextImageLayout.wrapLeft,
      'wrapRight' => CreateTextImageLayout.wrapRight,
      _ => CreateTextImageLayout.fullWidth,
    };
    return CreateTextBlock(
      id: (map['id'] ?? '').toString(),
      type: type,
      text: (map['text'] ?? '').toString(),
      imagePath: (map['imagePath'] ?? '').toString(),
      imageLayout: imageLayout,
    );
  }

  final String id;
  final CreateTextBlockType type;
  final String text;
  final String imagePath;
  final CreateTextImageLayout imageLayout;

  bool get isTextLike => type != CreateTextBlockType.image;
  bool get hasText => text.trim().isNotEmpty;
  bool get hasImage => imagePath.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == CreateTextImageLayout.wrapLeft ||
      imageLayout == CreateTextImageLayout.wrapRight;

  CreateTextBlock copyWith({
    String? id,
    CreateTextBlockType? type,
    String? text,
    String? imagePath,
    CreateTextImageLayout? imageLayout,
  }) {
    return CreateTextBlock(
      id: id ?? this.id,
      type: type ?? this.type,
      text: text ?? this.text,
      imagePath: imagePath ?? this.imagePath,
      imageLayout: imageLayout ?? this.imageLayout,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      'text': text,
      'imagePath': imagePath,
      'imageLayout': imageLayout.name,
    };
  }
}

List<CreateTextBlock> createDefaultArticleBlocks({
  String body = '',
  List<String> imagePaths = const <String>[],
}) {
  final blocks = <CreateTextBlock>[
    CreateTextBlock.paragraph(id: 'paragraph_0', text: body),
    ...imagePaths.asMap().entries.map(
      (entry) => CreateTextBlock.image(
        id: 'image_${entry.key}',
        imagePath: entry.value,
      ),
    ),
  ]
      .where(
        (block) =>
            block.hasImage ||
            block.text.isNotEmpty ||
            block.type == CreateTextBlockType.paragraph,
      )
      .toList(growable: false);
  if (blocks.isEmpty) {
    return const <CreateTextBlock>[
      CreateTextBlock(
        id: 'paragraph_0',
        type: CreateTextBlockType.paragraph,
      ),
    ];
  }
  return blocks;
}

String buildArticlePlainText(List<CreateTextBlock> blocks) {
  final lines = blocks
      .where((block) => block.isTextLike && block.hasText)
      .map((block) => block.text.trim())
      .toList(growable: false);
  return lines.join('\n');
}

List<String> extractArticleImagePaths(List<CreateTextBlock> blocks) {
  return blocks
      .where((block) => block.hasImage)
      .map((block) => block.imagePath.trim())
      .where((path) => path.isNotEmpty)
      .toList(growable: false);
}

@immutable
class CreateEditorStateV2 {
  const CreateEditorStateV2({
    required this.editorKind,
    required this.mediaKind,
    required this.imagePaths,
    required this.videoPath,
    required this.originalVideoPath,
    required this.videoThumbnail,
    required this.videoDurationMs,
    required this.videoTrimStartMs,
    required this.videoTrimEndMs,
    required this.videoCoverTimeMs,
    required this.videoMuted,
    required this.currentMediaIndex,
    required this.title,
    required this.body,
    required this.articleBlocks,
    required this.activeArticleBlockId,
    required this.titlePresentation,
    required this.titleHintDismissed,
    required this.settings,
    this.draftId,
  });

  factory CreateEditorStateV2.initial({
    CreateEditorKind editorKind = CreateEditorKind.text,
  }) {
    final initialBlocks = createDefaultArticleBlocks();
    return CreateEditorStateV2(
      editorKind: editorKind,
      mediaKind: CreateMediaKind.none,
      imagePaths: const <String>[],
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoMuted: false,
      currentMediaIndex: 0,
      title: '',
      body: '',
      articleBlocks: initialBlocks,
      activeArticleBlockId: initialBlocks.first.id,
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: const PublishSettings(),
    );
  }

  final CreateEditorKind editorKind;
  final CreateMediaKind mediaKind;
  final List<String> imagePaths;
  final String videoPath;
  final String originalVideoPath;
  final String videoThumbnail;
  final int videoDurationMs;
  final int videoTrimStartMs;
  final int videoTrimEndMs;
  final int videoCoverTimeMs;
  final bool videoMuted;
  final int currentMediaIndex;
  final String title;
  final String body;
  final List<CreateTextBlock> articleBlocks;
  final String? activeArticleBlockId;
  final TitlePresentation titlePresentation;
  final bool titleHintDismissed;
  final PublishSettings settings;
  final String? draftId;

  bool get hasImages => imagePaths.isNotEmpty;
  bool get hasVideo => videoPath.trim().isNotEmpty;
  bool get hasTitle => title.trim().isNotEmpty;
  bool get hasBody => body.trim().isNotEmpty;
  bool get hasContent => hasTitle || hasBody || hasImages || hasVideo;
  bool get hasArticleImages => extractArticleImagePaths(articleBlocks).isNotEmpty;
  bool get shouldSuggestTitle {
    if (hasTitle) {
      return false;
    }
    if (editorKind == CreateEditorKind.media) {
      return mediaKind == CreateMediaKind.video ||
          imagePaths.length >= 4 ||
          body.trim().length >= 80;
    }
    final paragraphCount = body
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
    return body.trim().length >= 140 ||
        paragraphCount >= 2 ||
        imagePaths.isNotEmpty;
  }

  CreateEditorStateV2 copyWith({
    CreateEditorKind? editorKind,
    CreateMediaKind? mediaKind,
    List<String>? imagePaths,
    String? videoPath,
    String? originalVideoPath,
    String? videoThumbnail,
    int? videoDurationMs,
    int? videoTrimStartMs,
    int? videoTrimEndMs,
    int? videoCoverTimeMs,
    bool? videoMuted,
    int? currentMediaIndex,
    String? title,
    String? body,
    List<CreateTextBlock>? articleBlocks,
    String? activeArticleBlockId,
    TitlePresentation? titlePresentation,
    bool? titleHintDismissed,
    PublishSettings? settings,
    String? draftId,
    bool clearDraftId = false,
    bool clearActiveArticleBlockId = false,
  }) {
    return CreateEditorStateV2(
      editorKind: editorKind ?? this.editorKind,
      mediaKind: mediaKind ?? this.mediaKind,
      imagePaths: imagePaths ?? this.imagePaths,
      videoPath: videoPath ?? this.videoPath,
      originalVideoPath: originalVideoPath ?? this.originalVideoPath,
      videoThumbnail: videoThumbnail ?? this.videoThumbnail,
      videoDurationMs: videoDurationMs ?? this.videoDurationMs,
      videoTrimStartMs: videoTrimStartMs ?? this.videoTrimStartMs,
      videoTrimEndMs: videoTrimEndMs ?? this.videoTrimEndMs,
      videoCoverTimeMs: videoCoverTimeMs ?? this.videoCoverTimeMs,
      videoMuted: videoMuted ?? this.videoMuted,
      currentMediaIndex: currentMediaIndex ?? this.currentMediaIndex,
      title: title ?? this.title,
      body: body ?? this.body,
      articleBlocks: articleBlocks ?? this.articleBlocks,
      activeArticleBlockId: clearActiveArticleBlockId
          ? null
          : (activeArticleBlockId ?? this.activeArticleBlockId),
      titlePresentation: titlePresentation ?? this.titlePresentation,
      titleHintDismissed: titleHintDismissed ?? this.titleHintDismissed,
      settings: settings ?? this.settings,
      draftId: clearDraftId ? null : (draftId ?? this.draftId),
    );
  }
}

@immutable
class CreateDraft {
  const CreateDraft({
    required this.id,
    required this.updatedAtMs,
    required this.state,
    this.sourceType,
  });

  final String id;
  final int updatedAtMs;
  final CreateEditorStateV2 state;
  final String? sourceType;

  factory CreateDraft.fromStorageMap(Map<String, dynamic> map) {
    final version = (map['draftVersion'] ?? '').toString().trim();
    if (version == 'v2') {
      return _fromV2Map(map);
    }
    return _fromLegacyMap(map);
  }

  static CreateDraft _fromV2Map(Map<String, dynamic> map) {
    final editorKind = (map['editorKind']?.toString() ?? 'text') == 'media'
        ? CreateEditorKind.media
        : CreateEditorKind.text;
    final mediaKindName = (map['mediaKind']?.toString() ?? 'none').trim();
    final mediaKind = switch (mediaKindName) {
      'images' => CreateMediaKind.images,
      'video' => CreateMediaKind.video,
      _ => CreateMediaKind.none,
    };
    final settingsMap = Map<String, dynamic>.from(
      map['settings'] as Map? ?? const <String, dynamic>{},
    );
    final storedBody = (map['body'] ?? '').toString();
    final storedImagePaths = List<String>.from(
      map['imagePaths'] as List? ?? const <String>[],
    );
    final articleBlocks = ((map['articleBlocks'] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map(
          (entry) => CreateTextBlock.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where((block) => block.id.trim().isNotEmpty)
        .toList(growable: false);
    final normalizedBlocks = articleBlocks.isNotEmpty
        ? articleBlocks
        : createDefaultArticleBlocks(
            body: storedBody,
            imagePaths: storedImagePaths,
          );
    final draftType = (map['type'] ?? editorKind.name).toString().trim();
    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      state: CreateEditorStateV2(
        editorKind: editorKind,
        mediaKind: mediaKind,
        imagePaths: editorKind == CreateEditorKind.text
            ? extractArticleImagePaths(normalizedBlocks)
            : storedImagePaths,
        videoPath: (map['videoPath'] ?? '').toString(),
        originalVideoPath: ((map['originalVideoPath'] ?? map['videoPath']) ?? '')
            .toString(),
        videoThumbnail: (map['videoThumbnail'] ?? '').toString(),
        videoDurationMs: (map['videoDurationMs'] as num?)?.toInt() ?? 0,
        videoTrimStartMs: (map['videoTrimStartMs'] as num?)?.toInt() ?? 0,
        videoTrimEndMs: (map['videoTrimEndMs'] as num?)?.toInt() ?? 0,
        videoCoverTimeMs: (map['videoCoverTimeMs'] as num?)?.toInt() ?? 0,
        videoMuted: map['videoMuted'] == true,
        currentMediaIndex:
            (map['currentMediaIndex'] as num?)?.toInt().clamp(0, 9999) ?? 0,
        title: (map['title'] ?? '').toString(),
        body: editorKind == CreateEditorKind.text
            ? buildArticlePlainText(normalizedBlocks)
            : storedBody,
        articleBlocks: normalizedBlocks,
        activeArticleBlockId:
            (map['activeArticleBlockId'] ?? '').toString().trim().isEmpty
            ? normalizedBlocks.first.id
            : (map['activeArticleBlockId'] ?? '').toString().trim(),
        titlePresentation:
            (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
            ? TitlePresentation.expanded
            : TitlePresentation.collapsed,
        titleHintDismissed: map['titleHintDismissed'] == true,
        settings: PublishSettings.fromMap(settingsMap),
        draftId: (map['id'] ?? '').toString(),
      ),
      sourceType: draftType,
    );
  }

  static CreateDraft _fromLegacyMap(Map<String, dynamic> map) {
    final tabKey = (map['type'] ?? 'moment').toString();
    final data = Map<String, dynamic>.from(
      map['data'] as Map? ?? const <String, dynamic>{},
    );
    final settings = PublishSettings.fromMap(data);

    late final CreateEditorStateV2 state;
    switch (tabKey) {
      case 'photo':
        final photoBlocks = createDefaultArticleBlocks(
          body: (data['description'] ?? '').toString(),
          imagePaths: List<String>.from(
            data['images'] as List? ?? const <String>[],
          ),
        );
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.media)
            .copyWith(
              mediaKind: CreateMediaKind.images,
              imagePaths: List<String>.from(
                data['images'] as List? ?? const <String>[],
              ),
              title: (data['title'] ?? '').toString(),
              body: (data['description'] ?? '').toString(),
              articleBlocks: photoBlocks,
              activeArticleBlockId: photoBlocks.first.id,
              titlePresentation:
                  ((data['title'] ?? '').toString().trim().isNotEmpty)
                  ? TitlePresentation.expanded
                  : TitlePresentation.collapsed,
              settings: settings,
              draftId: (map['id'] ?? '').toString(),
            );
        break;
      case 'video':
        final videoBlocks = createDefaultArticleBlocks(
          body: (data['description'] ?? '').toString(),
        );
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.media)
            .copyWith(
              mediaKind: CreateMediaKind.video,
              videoPath: (data['videoPath'] ?? '').toString(),
              originalVideoPath:
                  ((data['originalVideoPath'] ?? data['videoPath']) ?? '')
                      .toString(),
              videoThumbnail:
                  (data['thumbnail'] ?? data['videoThumbnail'] ?? '').toString(),
              videoDurationMs: (data['videoDurationMs'] as num?)?.toInt() ?? 0,
              videoTrimStartMs: (data['videoTrimStartMs'] as num?)?.toInt() ?? 0,
              videoTrimEndMs: (data['videoTrimEndMs'] as num?)?.toInt() ?? 0,
              videoCoverTimeMs: (data['videoCoverTimeMs'] as num?)?.toInt() ?? 0,
              videoMuted: data['videoMuted'] == true,
              title: (data['title'] ?? '').toString(),
              body: (data['description'] ?? '').toString(),
              articleBlocks: videoBlocks,
              activeArticleBlockId: videoBlocks.first.id,
              titlePresentation:
                  ((data['title'] ?? '').toString().trim().isNotEmpty)
                  ? TitlePresentation.expanded
                  : TitlePresentation.collapsed,
              settings: settings,
              draftId: (map['id'] ?? '').toString(),
            );
        break;
      case 'article':
        final articleBlocks = createDefaultArticleBlocks(
          body: (data['content'] ?? '').toString(),
          imagePaths: List<String>.from(
            data['covers'] as List? ?? const <String>[],
          ),
        );
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.text)
            .copyWith(
              imagePaths: extractArticleImagePaths(articleBlocks),
              title: (data['title'] ?? '').toString(),
              body: buildArticlePlainText(articleBlocks),
              articleBlocks: articleBlocks,
              activeArticleBlockId: articleBlocks.first.id,
              titlePresentation:
                  ((data['title'] ?? '').toString().trim().isNotEmpty)
                  ? TitlePresentation.expanded
                  : TitlePresentation.collapsed,
              settings: settings,
              draftId: (map['id'] ?? '').toString(),
            );
        break;
      case 'moment':
      default:
        final videoPath = (data['videoPath'] ?? '').toString();
        final originalVideoPath =
            ((data['originalVideoPath'] ?? data['videoPath']) ?? '').toString();
        final images = List<String>.from(
          data['images'] as List? ?? const <String>[],
        );
        final momentBlocks = createDefaultArticleBlocks(
          body: (data['content'] ?? '').toString(),
          imagePaths: images,
        );
        state = CreateEditorStateV2.initial(
          editorKind: videoPath.isNotEmpty || images.isNotEmpty
              ? CreateEditorKind.media
              : CreateEditorKind.text,
        ).copyWith(
          mediaKind: videoPath.isNotEmpty
              ? CreateMediaKind.video
              : (images.isNotEmpty ? CreateMediaKind.images : CreateMediaKind.none),
          imagePaths: images,
          videoPath: videoPath,
          originalVideoPath: originalVideoPath,
          videoThumbnail: (data['videoThumbnail'] ?? '').toString(),
          videoDurationMs: (data['videoDurationMs'] as num?)?.toInt() ?? 0,
          videoTrimStartMs: (data['videoTrimStartMs'] as num?)?.toInt() ?? 0,
          videoTrimEndMs: (data['videoTrimEndMs'] as num?)?.toInt() ?? 0,
          videoCoverTimeMs: (data['videoCoverTimeMs'] as num?)?.toInt() ?? 0,
          videoMuted: data['videoMuted'] == true,
          body: videoPath.isNotEmpty || images.isNotEmpty
              ? (data['content'] ?? '').toString()
              : buildArticlePlainText(momentBlocks),
          articleBlocks: momentBlocks,
          activeArticleBlockId: momentBlocks.first.id,
          settings: settings,
          draftId: (map['id'] ?? '').toString(),
        );
        break;
    }

    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      state: state,
      sourceType: tabKey,
    );
  }

  Map<String, dynamic> toStorageMap() {
    return <String, dynamic>{
      'id': id,
      'type': storageType,
      'updatedAt': updatedAtMs,
      'identity': identity.value,
      'draftVersion': 'v2',
      'editorKind': state.editorKind.name,
      'mediaKind': state.mediaKind.name,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoMuted': state.videoMuted,
      'currentMediaIndex': state.currentMediaIndex,
      'title': state.title,
      'body': state.body,
      'articleBlocks': state.articleBlocks
          .map((block) => block.toMap())
          .toList(growable: false),
      'activeArticleBlockId': state.activeArticleBlockId,
      'titlePresentation': state.titlePresentation.name,
      'titleHintDismissed': state.titleHintDismissed,
      'settings': state.settings.toMap(),
      'data': data,
    };
  }

  String get storageType {
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ? 'video' : 'media';
    }
    return 'text';
  }

  String get tabKey {
    if (sourceType != null && sourceType!.isNotEmpty) {
      return sourceType!;
    }
    return storageType;
  }

  CreateContentIdentity get identity {
    switch (tabKey) {
      case 'media':
      case 'photo':
      case 'video':
      case 'article':
        return CreateContentIdentity.work;
      default:
        return CreateContentIdentity.moment;
    }
  }

  Map<String, dynamic> get data {
    return <String, dynamic>{
      ...state.settings.toMap(),
      'title': state.title,
      'body': state.body,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoMuted': state.videoMuted,
    };
  }

  String get previewText {
    final primary = state.title.trim();
    if (primary.isNotEmpty) {
      return primary;
    }
    return state.body.trim();
  }

  String get draftLabel {
    if (state.editorKind == CreateEditorKind.media) {
      return '媒体草稿';
    }
    if (state.title.trim().isNotEmpty || state.imagePaths.isNotEmpty) {
      return '文章草稿';
    }
    return '文字草稿';
  }

  bool get shouldSuggestTitle {
    if (state.title.trim().isNotEmpty) {
      return false;
    }
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ||
          state.imagePaths.length >= 4 ||
          state.body.trim().length >= 80;
    }
    final body = state.body.trim();
    final paragraphCount = body
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
    return body.length >= 140 || paragraphCount >= 2 || state.imagePaths.isNotEmpty;
  }
}
