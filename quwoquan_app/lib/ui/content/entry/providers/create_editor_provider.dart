import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

/// 创作页编辑器状态
class CreateEditorState {
  final Map<String, dynamic> data;
  final String currentTab;
  final bool isMomentEditing;
  final bool isPhotoEditing;

  const CreateEditorState({
    required this.data,
    required this.currentTab,
    this.isMomentEditing = false,
    this.isPhotoEditing = false,
  });

  factory CreateEditorState.initial() {
    return CreateEditorState(
      data: {
        'moment': {
          'content': '',
          'images': <String>[],
          'videoPath': '',
          'videoThumbnail': '',
          'durationMs': 0,
          'contentIdentity': CreateContentIdentity.moment.value,
          'visibility': 'public',
          'assistantUsePolicy': 'inherit',
          'circleIds': <String>[],
          'circleNames': <String>[],
          'locationName': '',
          'location': <String, dynamic>{},
        },
        'photo': {
          'title': '',
          'description': '',
          'images': <String>[],
          'contentIdentity': CreateContentIdentity.work.value,
          'visibility': 'public',
          'assistantUsePolicy': 'inherit',
          'circleIds': <String>[],
          'circleNames': <String>[],
          'locationName': '',
          'location': <String, dynamic>{},
        },
        'video': {
          'title': '',
          'description': '',
          'videoPath': '',
          'thumbnail': '',
          'durationMs': 0,
          'storyboardImages': <String>[],
          'contentIdentity': CreateContentIdentity.work.value,
          'visibility': 'public',
          'assistantUsePolicy': 'inherit',
          'circleIds': <String>[],
          'circleNames': <String>[],
          'locationName': '',
          'location': <String, dynamic>{},
        },
        'article': {
          'title': '',
          'content': '',
          'covers': <String>[],
          'contentIdentity': CreateContentIdentity.work.value,
          'visibility': 'public',
          'assistantUsePolicy': 'inherit',
          'circleIds': <String>[],
          'circleNames': <String>[],
          'locationName': '',
          'location': <String, dynamic>{},
        },
      },
      currentTab: 'moment',
    );
  }

  CreateEditorState copyWith({
    Map<String, dynamic>? data,
    String? currentTab,
    bool? isMomentEditing,
    bool? isPhotoEditing,
  }) {
    return CreateEditorState(
      data: data ?? this.data,
      currentTab: currentTab ?? this.currentTab,
      isMomentEditing: isMomentEditing ?? this.isMomentEditing,
      isPhotoEditing: isPhotoEditing ?? this.isPhotoEditing,
    );
  }

  Map<String, dynamic> get currentTabData =>
      data[currentTab] as Map<String, dynamic>? ?? {};
}

class CreateEditorNotifier extends Notifier<CreateEditorState> {
  @override
  CreateEditorState build() {
    return CreateEditorState.initial();
  }

  void updateTabData(String tab, Map<String, dynamic> newData) {
    final nextData = Map<String, dynamic>.from(state.data);
    nextData[tab] = newData;
    state = state.copyWith(data: nextData);
  }

  void updateCurrentTabData(Map<String, dynamic> newData) {
    updateTabData(state.currentTab, newData);
  }

  void updateField(String tab, String key, dynamic value) {
    final tabData = Map<String, dynamic>.from(state.data[tab] ?? {});
    tabData[key] = value;
    updateTabData(tab, tabData);
  }
  
  void updateCurrentTabField(String key, dynamic value) {
    updateField(state.currentTab, key, value);
  }

  void setTab(String tab) {
    if (state.currentTab == tab) return;
    state = state.copyWith(currentTab: tab);
  }

  void setMomentEditing(bool value) {
    state = state.copyWith(isMomentEditing: value);
  }

  void setPhotoEditing(bool value) {
    state = state.copyWith(isPhotoEditing: value);
  }

  void restoreFromDraft(CreateDraft draft) {
    final nextData = Map<String, dynamic>.from(state.data);
    nextData[draft.tabKey] = draft.data;
    state = state.copyWith(
      data: nextData,
      currentTab: draft.tabKey,
      isMomentEditing: false,
      isPhotoEditing: false,
    );
  }
  
  void reset() {
    state = CreateEditorState.initial();
  }
}

final createEditorProvider =
    NotifierProvider.autoDispose<CreateEditorNotifier, CreateEditorState>(
  CreateEditorNotifier.new,
);
