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

@immutable
class CreateEditorStateV2 {
  const CreateEditorStateV2({
    required this.editorKind,
    required this.mediaKind,
    required this.imagePaths,
    required this.videoPath,
    required this.videoThumbnail,
    required this.currentMediaIndex,
    required this.title,
    required this.body,
    required this.titlePresentation,
    required this.titleHintDismissed,
    required this.settings,
    this.draftId,
  });

  factory CreateEditorStateV2.initial({
    CreateEditorKind editorKind = CreateEditorKind.text,
  }) {
    return CreateEditorStateV2(
      editorKind: editorKind,
      mediaKind: CreateMediaKind.none,
      imagePaths: const <String>[],
      videoPath: '',
      videoThumbnail: '',
      currentMediaIndex: 0,
      title: '',
      body: '',
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: const PublishSettings(),
    );
  }

  final CreateEditorKind editorKind;
  final CreateMediaKind mediaKind;
  final List<String> imagePaths;
  final String videoPath;
  final String videoThumbnail;
  final int currentMediaIndex;
  final String title;
  final String body;
  final TitlePresentation titlePresentation;
  final bool titleHintDismissed;
  final PublishSettings settings;
  final String? draftId;

  bool get hasImages => imagePaths.isNotEmpty;
  bool get hasVideo => videoPath.trim().isNotEmpty;
  bool get hasTitle => title.trim().isNotEmpty;
  bool get hasBody => body.trim().isNotEmpty;
  bool get hasContent => hasTitle || hasBody || hasImages || hasVideo;
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
    String? videoThumbnail,
    int? currentMediaIndex,
    String? title,
    String? body,
    TitlePresentation? titlePresentation,
    bool? titleHintDismissed,
    PublishSettings? settings,
    String? draftId,
    bool clearDraftId = false,
  }) {
    return CreateEditorStateV2(
      editorKind: editorKind ?? this.editorKind,
      mediaKind: mediaKind ?? this.mediaKind,
      imagePaths: imagePaths ?? this.imagePaths,
      videoPath: videoPath ?? this.videoPath,
      videoThumbnail: videoThumbnail ?? this.videoThumbnail,
      currentMediaIndex: currentMediaIndex ?? this.currentMediaIndex,
      title: title ?? this.title,
      body: body ?? this.body,
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
    final draftType = (map['type'] ?? editorKind.name).toString().trim();
    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      state: CreateEditorStateV2(
        editorKind: editorKind,
        mediaKind: mediaKind,
        imagePaths: List<String>.from(
          map['imagePaths'] as List? ?? const <String>[],
        ),
        videoPath: (map['videoPath'] ?? '').toString(),
        videoThumbnail: (map['videoThumbnail'] ?? '').toString(),
        currentMediaIndex:
            (map['currentMediaIndex'] as num?)?.toInt().clamp(0, 9999) ?? 0,
        title: (map['title'] ?? '').toString(),
        body: (map['body'] ?? '').toString(),
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
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.media)
            .copyWith(
              mediaKind: CreateMediaKind.images,
              imagePaths: List<String>.from(
                data['images'] as List? ?? const <String>[],
              ),
              title: (data['title'] ?? '').toString(),
              body: (data['description'] ?? '').toString(),
              titlePresentation:
                  ((data['title'] ?? '').toString().trim().isNotEmpty)
                  ? TitlePresentation.expanded
                  : TitlePresentation.collapsed,
              settings: settings,
              draftId: (map['id'] ?? '').toString(),
            );
        break;
      case 'video':
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.media)
            .copyWith(
              mediaKind: CreateMediaKind.video,
              videoPath: (data['videoPath'] ?? '').toString(),
              videoThumbnail:
                  (data['thumbnail'] ?? data['videoThumbnail'] ?? '').toString(),
              title: (data['title'] ?? '').toString(),
              body: (data['description'] ?? '').toString(),
              titlePresentation:
                  ((data['title'] ?? '').toString().trim().isNotEmpty)
                  ? TitlePresentation.expanded
                  : TitlePresentation.collapsed,
              settings: settings,
              draftId: (map['id'] ?? '').toString(),
            );
        break;
      case 'article':
        state = CreateEditorStateV2.initial(editorKind: CreateEditorKind.text)
            .copyWith(
              imagePaths: List<String>.from(
                data['covers'] as List? ?? const <String>[],
              ),
              title: (data['title'] ?? '').toString(),
              body: (data['content'] ?? '').toString(),
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
        final images = List<String>.from(
          data['images'] as List? ?? const <String>[],
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
          videoThumbnail: (data['videoThumbnail'] ?? '').toString(),
          body: (data['content'] ?? '').toString(),
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
      'videoThumbnail': state.videoThumbnail,
      'currentMediaIndex': state.currentMediaIndex,
      'title': state.title,
      'body': state.body,
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
      'videoThumbnail': state.videoThumbnail,
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
