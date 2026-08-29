// Code generated from canonical Search metadata. DO NOT EDIT.
// Sources: _shared/search_contract.yaml, _shared/search_objects.yaml

library;

enum SearchObjectType {
  webDocument('web.document'),
  chatContact('chat.contact'),
  chatConversation('chat.conversation'),
  chatMessage('chat.message'),
  circleGroup('circle.group'),
  circleCircle('circle.circle'),
  contentPost('content.post'),
  locationPlace('location.place'),
  entityHomepage('entity.homepage'),
  userProfile('user.profile'),
  tag('tag'),
  integrationLocationPoi('integration.location_poi');

  const SearchObjectType(this.wireValue);

  final String wireValue;

  static SearchObjectType? fromWire(String? value) {
    switch ((value ?? '').trim()) {
      case 'web.document':
        return SearchObjectType.webDocument;
      case 'chat.contact':
        return SearchObjectType.chatContact;
      case 'chat.conversation':
        return SearchObjectType.chatConversation;
      case 'chat.message':
        return SearchObjectType.chatMessage;
      case 'circle.group':
        return SearchObjectType.circleGroup;
      case 'circle.circle':
        return SearchObjectType.circleCircle;
      case 'content.post':
        return SearchObjectType.contentPost;
      case 'location.place':
        return SearchObjectType.locationPlace;
      case 'entity.homepage':
        return SearchObjectType.entityHomepage;
      case 'user.profile':
        return SearchObjectType.userProfile;
      case 'tag':
        return SearchObjectType.tag;
      case 'integration.location_poi':
        return SearchObjectType.integrationLocationPoi;
      default:
        return null;
    }
  }
}

enum RetrieveTarget {
  article('article'),
  photo('photo'),
  video('video'),
  user('user'),
  entity('entity'),
  location('location'),
  circle('circle'),
  group('group'),
  chat('chat');

  const RetrieveTarget(this.wireValue);

  final String wireValue;

  static RetrieveTarget? fromWire(String? value) {
    switch ((value ?? '').trim()) {
      case 'article':
        return RetrieveTarget.article;
      case 'photo':
        return RetrieveTarget.photo;
      case 'video':
        return RetrieveTarget.video;
      case 'user':
        return RetrieveTarget.user;
      case 'entity':
        return RetrieveTarget.entity;
      case 'location':
        return RetrieveTarget.location;
      case 'circle':
        return RetrieveTarget.circle;
      case 'group':
        return RetrieveTarget.group;
      case 'chat':
        return RetrieveTarget.chat;
      default:
        return null;
    }
  }
}

enum SearchConversationType {
  direct('direct'),
  group('group');

  const SearchConversationType(this.wireValue);

  final String wireValue;

  static SearchConversationType? fromWire(String? value) {
    switch ((value ?? '').trim()) {
      case 'direct':
        return SearchConversationType.direct;
      case 'group':
        return SearchConversationType.group;
      default:
        return null;
    }
  }
}

// ignore: avoid_classes_with_only_static_members
final class RetrieveToolContract {
  const RetrieveToolContract._();

  static const List<String> forbiddenFields = <String>[
    'type',
    'relation',
    'anchors',
    'kind',
    'mode',
    'strategy',
    'purpose',
    'visibility',
    'fields',
    'where',
    'query',
    'objectTypes',
    'contentTypes',
    'tags',
    'timeRange',
  ];
}
