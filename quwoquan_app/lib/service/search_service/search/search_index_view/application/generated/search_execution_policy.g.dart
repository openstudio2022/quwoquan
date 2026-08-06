// Code generated from canonical Search metadata. DO NOT EDIT.
// Sources: _shared/search_contract.yaml, _shared/search_objects.yaml

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show RetrieveTarget, SearchObjectType;

enum SearchExecutionStrategy {
  localOnly('local_only'),
  remoteOnly('remote_only'),
  hybridRemoteFallbackLocal('hybrid_remote_fallback_local'),
  filterOnly('filter_only'),
  ;

  const SearchExecutionStrategy(this.wireValue);

  final String wireValue;

  static SearchExecutionStrategy? fromWire(String? value) {
    switch ((value ?? '').trim()) {
      case 'local_only':
        return SearchExecutionStrategy.localOnly;
      case 'remote_only':
        return SearchExecutionStrategy.remoteOnly;
      case 'hybrid_remote_fallback_local':
        return SearchExecutionStrategy.hybridRemoteFallbackLocal;
      case 'filter_only':
        return SearchExecutionStrategy.filterOnly;
      default:
        return null;
    }
  }
}

// ignore: avoid_classes_with_only_static_members
final class SearchContractDefaults {
  const SearchContractDefaults._();

  static const int suggestLimit = 12;
  static const int resultLimit = 20;
  static const int assistantLimit = 8;
}

final class SearchObjectExecutionPolicy {
  const SearchObjectExecutionPolicy({
    required this.type,
    required this.domain,
    required this.strategy,
    required this.provider,
  });

  final SearchObjectType type;
  final String domain;
  final SearchExecutionStrategy strategy;
  final String provider;
}

final class SearchRetrieveTargetPolicy {
  const SearchRetrieveTargetPolicy({
    required this.target,
    required this.objectType,
    required this.contentType,
  });

  final RetrieveTarget target;
  final SearchObjectType objectType;
  final String contentType;
}

// ignore: avoid_classes_with_only_static_members
final class SearchExecutionPolicy {
  const SearchExecutionPolicy._();

  static const List<SearchObjectExecutionPolicy> objectTypes =
      <SearchObjectExecutionPolicy>[
    SearchObjectExecutionPolicy(
      type: SearchObjectType.webDocument,
      domain: 'external',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'web_search',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.chatContact,
      domain: 'messages',
      strategy: SearchExecutionStrategy.localOnly,
      provider: 'chat_local',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.chatConversation,
      domain: 'messages',
      strategy: SearchExecutionStrategy.localOnly,
      provider: 'chat_local',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.chatMessage,
      domain: 'messages',
      strategy: SearchExecutionStrategy.localOnly,
      provider: 'chat_local',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.circleGroup,
      domain: 'circle',
      strategy: SearchExecutionStrategy.hybridRemoteFallbackLocal,
      provider: 'circle_remote_local',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.circleCircle,
      domain: 'circle',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'circle_remote',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.contentPost,
      domain: 'content',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'content_remote',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.locationPlace,
      domain: 'content',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'content_remote',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.entityHomepage,
      domain: 'entity',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'homepage_remote',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.userProfile,
      domain: 'user',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'user_profile_remote',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.tag,
      domain: 'tag',
      strategy: SearchExecutionStrategy.filterOnly,
      provider: 'taxonomy_filter',
    ),
    SearchObjectExecutionPolicy(
      type: SearchObjectType.integrationLocationPoi,
      domain: 'integration',
      strategy: SearchExecutionStrategy.remoteOnly,
      provider: 'location_remote',
    ),
  ];

  static const List<SearchRetrieveTargetPolicy> retrieveTargets =
      <SearchRetrieveTargetPolicy>[
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.article,
      objectType: SearchObjectType.contentPost,
      contentType: 'article',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.photo,
      objectType: SearchObjectType.contentPost,
      contentType: 'image',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.video,
      objectType: SearchObjectType.contentPost,
      contentType: 'video',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.user,
      objectType: SearchObjectType.userProfile,
      contentType: '',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.entity,
      objectType: SearchObjectType.entityHomepage,
      contentType: '',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.location,
      objectType: SearchObjectType.locationPlace,
      contentType: '',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.circle,
      objectType: SearchObjectType.circleCircle,
      contentType: '',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.group,
      objectType: SearchObjectType.circleGroup,
      contentType: '',
    ),
    SearchRetrieveTargetPolicy(
      target: RetrieveTarget.chat,
      objectType: SearchObjectType.chatMessage,
      contentType: '',
    ),
  ];

  static SearchObjectExecutionPolicy? objectPolicyFor(
    SearchObjectType type,
  ) {
    for (final policy in objectTypes) {
      if (policy.type == type) return policy;
    }
    return null;
  }

  static SearchRetrieveTargetPolicy? retrievePolicyFor(
    RetrieveTarget target,
  ) {
    for (final policy in retrieveTargets) {
      if (policy.target == target) return policy;
    }
    return null;
  }
}
