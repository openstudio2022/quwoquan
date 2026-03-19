import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

class CreateEditorNotifier extends Notifier<CreateEditorStateV2> {
  @override
  CreateEditorStateV2 build() {
    return CreateEditorStateV2.initial();
  }

  void reset({CreateEditorKind editorKind = CreateEditorKind.text}) {
    state = CreateEditorStateV2.initial(editorKind: editorKind);
  }

  void setEditorKind(CreateEditorKind editorKind) {
    state = state.copyWith(editorKind: editorKind);
  }

  void setStartAction(EditorStartAction? action) {
    switch (action) {
      case EditorStartAction.gallery:
      case EditorStartAction.capture:
        state = state.copyWith(editorKind: CreateEditorKind.media);
        return;
      case EditorStartAction.write:
      case null:
        state = state.copyWith(editorKind: CreateEditorKind.text);
        return;
    }
  }

  void updateTitle(String value) {
    state = state.copyWith(
      title: value,
      titlePresentation: value.trim().isEmpty
          ? state.titlePresentation
          : TitlePresentation.expanded,
    );
  }

  void updateBody(String value) {
    state = state.copyWith(body: value);
  }

  void expandTitle() {
    state = state.copyWith(titlePresentation: TitlePresentation.expanded);
  }

  void collapseTitleIfEmpty() {
    if (state.title.trim().isNotEmpty) {
      return;
    }
    state = state.copyWith(titlePresentation: TitlePresentation.collapsed);
  }

  void dismissTitleHint() {
    state = state.copyWith(titleHintDismissed: true);
  }

  void restoreTitleHint() {
    state = state.copyWith(titleHintDismissed: false);
  }

  void setSettings(PublishSettings settings) {
    state = state.copyWith(settings: settings);
  }

  void setCurrentMediaIndex(int index) {
    final maxIndex = state.hasVideo
        ? 0
        : (state.imagePaths.isEmpty ? 0 : state.imagePaths.length - 1);
    state = state.copyWith(currentMediaIndex: index.clamp(0, maxIndex));
  }

  void setDraftId(String? id) {
    state = state.copyWith(draftId: id, clearDraftId: id == null);
  }

  void setImages(
    List<String> paths, {
    required CreateEditorKind editorKind,
    int currentIndex = 0,
  }) {
    final sanitized = paths
        .map((path) => path.trim())
        .where((path) => path.isNotEmpty)
        .toList(growable: false);
    state = state.copyWith(
      editorKind: editorKind,
      mediaKind: sanitized.isEmpty ? CreateMediaKind.none : CreateMediaKind.images,
      imagePaths: sanitized,
      videoPath: '',
      videoThumbnail: '',
      currentMediaIndex: sanitized.isEmpty
          ? 0
          : currentIndex.clamp(0, sanitized.length - 1),
    );
  }

  void appendImages(
    List<String> paths, {
    required CreateEditorKind editorKind,
    int maxImages = 20,
  }) {
    final merged = <String>[
      ...state.imagePaths,
      ...paths.map((path) => path.trim()).where((path) => path.isNotEmpty),
    ];
    setImages(
      merged.take(maxImages).toList(growable: false),
      editorKind: editorKind,
      currentIndex: state.imagePaths.isEmpty ? 0 : state.currentMediaIndex,
    );
  }

  void removeImageAt(int index) {
    if (index < 0 || index >= state.imagePaths.length) {
      return;
    }
    final next = List<String>.from(state.imagePaths)..removeAt(index);
    setImages(
      next,
      editorKind: state.editorKind,
      currentIndex: state.currentMediaIndex > index
          ? state.currentMediaIndex - 1
          : state.currentMediaIndex,
    );
  }

  void reorderImages(int oldIndex, int newIndex) {
    if (oldIndex < 0 ||
        oldIndex >= state.imagePaths.length ||
        newIndex < 0 ||
        newIndex > state.imagePaths.length ||
        oldIndex == newIndex) {
      return;
    }
    final currentCoverPath = state.imagePaths[
        state.currentMediaIndex.clamp(0, state.imagePaths.length - 1)];
    final next = List<String>.from(state.imagePaths);
    final moved = next.removeAt(oldIndex);
    final targetIndex = oldIndex < newIndex ? newIndex - 1 : newIndex;
    next.insert(targetIndex, moved);
    final nextCoverIndex = next.indexOf(currentCoverPath);
    state = state.copyWith(
      imagePaths: next,
      mediaKind: next.isEmpty ? CreateMediaKind.none : CreateMediaKind.images,
      currentMediaIndex: nextCoverIndex < 0 ? 0 : nextCoverIndex,
    );
  }

  void clearImages() {
    setImages(const <String>[], editorKind: state.editorKind);
  }

  void setVideo(
    String path, {
    required CreateEditorKind editorKind,
    String thumbnail = '',
  }) {
    state = state.copyWith(
      editorKind: editorKind,
      mediaKind: path.trim().isEmpty ? CreateMediaKind.none : CreateMediaKind.video,
      imagePaths: const <String>[],
      videoPath: path.trim(),
      videoThumbnail: thumbnail.trim(),
      currentMediaIndex: 0,
    );
  }

  void clearVideo() {
    state = state.copyWith(
      mediaKind: state.imagePaths.isNotEmpty ? CreateMediaKind.images : CreateMediaKind.none,
      videoPath: '',
      videoThumbnail: '',
      currentMediaIndex: 0,
    );
  }

  void restoreFromDraft(CreateDraft draft) {
    state = draft.state.copyWith(draftId: draft.id);
  }
}

final createEditorProvider =
    NotifierProvider.autoDispose<CreateEditorNotifier, CreateEditorStateV2>(
  CreateEditorNotifier.new,
);
