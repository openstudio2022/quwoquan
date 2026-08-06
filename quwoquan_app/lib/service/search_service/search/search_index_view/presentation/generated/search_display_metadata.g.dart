// Code generated from canonical Search metadata. DO NOT EDIT.
// Source: _shared/search_objects.yaml

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show RetrieveTarget, SearchObjectType;

final class SearchObjectDisplayMetadata {
  const SearchObjectDisplayMetadata({required this.type, required this.label});

  final SearchObjectType type;
  final String label;
}

final class SearchSectionDisplayMetadata {
  const SearchSectionDisplayMetadata({
    required this.id,
    required this.title,
    required this.defaultObjectTypes,
  });

  final String id;
  final String title;
  final List<SearchObjectType> defaultObjectTypes;
}

final class SearchRetrieveTargetDisplayMetadata {
  const SearchRetrieveTargetDisplayMetadata({
    required this.target,
    required this.label,
  });

  final RetrieveTarget target;
  final String label;
}

// ignore: avoid_classes_with_only_static_members
final class SearchDisplayMetadata {
  const SearchDisplayMetadata._();

  static const List<SearchObjectDisplayMetadata> objectTypes =
      <SearchObjectDisplayMetadata>[
    SearchObjectDisplayMetadata(
      type: SearchObjectType.webDocument,
      label: '网页',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.chatContact,
      label: '联系人',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.chatConversation,
      label: '聊天会话',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.chatMessage,
      label: '聊天消息',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.circleGroup,
      label: '讨论',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.circleCircle,
      label: '圈子',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.contentPost,
      label: '内容',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.locationPlace,
      label: '地点',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.entityHomepage,
      label: '主页',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.userProfile,
      label: '用户',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.tag,
      label: '标签',
    ),
    SearchObjectDisplayMetadata(
      type: SearchObjectType.integrationLocationPoi,
      label: '位置',
    ),
  ];

  static const List<SearchSectionDisplayMetadata> sections =
      <SearchSectionDisplayMetadata>[
    SearchSectionDisplayMetadata(
      id: 'contacts',
      title: '联系人',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.chatContact],
    ),
    SearchSectionDisplayMetadata(
      id: 'chat_records',
      title: '聊天记录',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.chatConversation, SearchObjectType.chatMessage],
    ),
    SearchSectionDisplayMetadata(
      id: 'groups',
      title: '讨论',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.circleGroup, SearchObjectType.circleCircle],
    ),
    SearchSectionDisplayMetadata(
      id: 'content',
      title: '内容',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.contentPost],
    ),
    SearchSectionDisplayMetadata(
      id: 'homepages',
      title: '主页',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.entityHomepage],
    ),
    SearchSectionDisplayMetadata(
      id: 'locations',
      title: '位置',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.locationPlace, SearchObjectType.integrationLocationPoi],
    ),
    SearchSectionDisplayMetadata(
      id: 'web',
      title: '网页',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.webDocument],
    ),
    SearchSectionDisplayMetadata(
      id: 'users',
      title: '用户',
      defaultObjectTypes: <SearchObjectType>[SearchObjectType.userProfile],
    ),
  ];

  static const List<SearchRetrieveTargetDisplayMetadata> retrieveTargets =
      <SearchRetrieveTargetDisplayMetadata>[
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.article,
      label: '文章',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.photo,
      label: '图文',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.video,
      label: '视频',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.user,
      label: '用户',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.entity,
      label: '实体主页',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.location,
      label: '地点',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.circle,
      label: '圈子',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.group,
      label: '讨论',
    ),
    SearchRetrieveTargetDisplayMetadata(
      target: RetrieveTarget.chat,
      label: '聊天',
    ),
  ];

  static SearchObjectDisplayMetadata? objectFor(SearchObjectType type) {
    for (final item in objectTypes) {
      if (item.type == type) return item;
    }
    return null;
  }

  static SearchSectionDisplayMetadata? sectionFor(String id) {
    for (final item in sections) {
      if (item.id == id) return item;
    }
    return null;
  }
}
