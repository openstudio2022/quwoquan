import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';

/// 关系能力位投影 DTO
/// 对应 GET /v1/user/{userId}/relationship/capability
/// 端侧消费方：用户主页动作矩阵、RTC 门禁、私信/打招呼入口
class RelationshipCapabilityDto {
  RelationshipCapabilityDto({
    required this.viewerSubAccountId,
    required this.targetSubAccountId,
    String? relationState,
    bool? canFollow,
    bool? canUnfollow,
    bool? canFollowBack,
    bool? canGreet,
    bool? canCreateDirectConversation,
    bool? canSendMessage,
    bool? canOpenConversation,
    bool? hasPendingGreeting,
    bool? hasFormalConversation,
    bool? canStartVoiceCall,
    bool? canStartVideoCall,
    bool? isBlocked,
    bool? isBlockedBy,
  })  : relationState = _normalizeRelationState(relationState ?? 'not_following'),
        canFollow = canFollow ??
            _defaultCanFollow(_normalizeRelationState(relationState ?? 'not_following')),
        canUnfollow = canUnfollow ??
            _defaultCanUnfollow(_normalizeRelationState(relationState ?? 'not_following')),
        canFollowBack = canFollowBack ??
            _defaultCanFollowBack(_normalizeRelationState(relationState ?? 'not_following')),
        canGreet = canGreet ??
            _defaultCanGreet(
              _normalizeRelationState(relationState ?? 'not_following'),
              isBlocked: isBlocked ?? false,
              isBlockedBy: isBlockedBy ?? false,
            ),
        canCreateDirectConversation = canCreateDirectConversation ?? false,
        canSendMessage = canSendMessage ?? false,
        canOpenConversation = canOpenConversation ?? canCreateDirectConversation ?? false,
        hasPendingGreeting = hasPendingGreeting ?? false,
        hasFormalConversation = hasFormalConversation ?? false,
        canStartVoiceCall = canStartVoiceCall ?? false,
        canStartVideoCall = canStartVideoCall ?? false,
        isBlocked = isBlocked ?? false,
        isBlockedBy = isBlockedBy ?? false;

  final String viewerSubAccountId;
  final String targetSubAccountId;

  /// 统一关系态：self | not_following | following | followed_by | mutual
  final String relationState;

  final bool canFollow;
  final bool canUnfollow;
  final bool canFollowBack;
  final bool canGreet;
  final bool canCreateDirectConversation;
  final bool canSendMessage;
  final bool canOpenConversation;
  final bool hasPendingGreeting;
  final bool hasFormalConversation;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;
  final bool isBlocked;
  final bool isBlockedBy;

  bool get isSelf => relationState == 'self';
  bool get isMutual => relationState == 'mutual';
  bool get isFollowing => relationState == 'following';
  bool get isFollowedBy => relationState == 'followed_by';
  bool get isNotFollowing => relationState == 'not_following';
  bool get viewerFollowsTarget => isFollowing || isMutual;
  bool get targetFollowsViewer => isFollowedBy || isMutual;

  static String _normalizeRelationState(String raw) {
    switch (raw) {
      case 'self':
        return 'self';
      case 'mutual':
        return 'mutual';
      case 'following':
        return 'following';
      case 'followed_by':
        return 'followed_by';
      case 'not_following':
      default:
        return 'not_following';
    }
  }

  static bool _defaultCanFollow(String relationState) {
    return relationState == 'not_following' || relationState == 'followed_by';
  }

  static bool _defaultCanUnfollow(String relationState) {
    return relationState == 'following' || relationState == 'mutual';
  }

  static bool _defaultCanFollowBack(String relationState) {
    return relationState == 'followed_by';
  }

  static bool _defaultCanGreet(
    String relationState, {
    required bool isBlocked,
    required bool isBlockedBy,
  }) {
    if (isBlocked || isBlockedBy || relationState == 'self' || relationState == 'mutual') {
      return false;
    }
    return true;
  }

  factory RelationshipCapabilityDto.fromRelationshipCapabilityWire(
    RelationshipCapabilityWireDto w,
  ) {
    return RelationshipCapabilityDto(
      viewerSubAccountId: w.viewerSubAccountId,
      targetSubAccountId: w.targetSubAccountId,
      relationState: w.relationState,
      canFollow: w.canFollow,
      canUnfollow: w.canUnfollow,
      canFollowBack: w.canFollowBack,
      canGreet: w.canGreet,
      canCreateDirectConversation: w.canCreateDirectConversation,
      canSendMessage: w.canSendMessage,
      canOpenConversation: w.canOpenConversation,
      hasPendingGreeting: w.hasPendingGreeting,
      hasFormalConversation: w.hasFormalConversation,
      canStartVoiceCall: w.canStartVoiceCall,
      canStartVideoCall: w.canStartVideoCall,
      isBlocked: w.isBlocked,
      isBlockedBy: w.isBlockedBy,
    );
  }

  factory RelationshipCapabilityDto.fromMap(Map<String, dynamic> map) {
    return RelationshipCapabilityDto.fromRelationshipCapabilityWire(
      RelationshipCapabilityWireDto.fromMap(map),
    );
  }

  /// 本地推导：由关注/被关注布尔量合成 [RelationshipCapabilityDto]（Mock 与乐观 UI 更新）。
  factory RelationshipCapabilityDto.fromFollowFlags({
    required String viewerId,
    required String targetId,
    required bool isFollowing,
    required bool isFollowedBy,
    bool isSelf = false,
    bool isBlocked = false,
    bool isBlockedBy = false,
    bool hasFormalConversation = false,
    bool hasPendingGreeting = false,
  }) {
    final isMutual = isFollowing && isFollowedBy;
    final relationState = isSelf
        ? 'self'
        : isMutual
            ? 'mutual'
            : isFollowing
                ? 'following'
                : isFollowedBy
                    ? 'followed_by'
                    : 'not_following';

    final blocked = isBlocked || isBlockedBy;
    final canCreateDirect = !blocked && isMutual;
    final canSend = !blocked && (isMutual || hasFormalConversation);
    final canGreet = !blocked &&
        !isSelf &&
        !isMutual &&
        !hasPendingGreeting &&
        !hasFormalConversation;

    return RelationshipCapabilityDto(
      viewerSubAccountId: viewerId,
      targetSubAccountId: targetId,
      relationState: relationState,
      canGreet: canGreet,
      canCreateDirectConversation: canCreateDirect,
      canSendMessage: canSend,
      canOpenConversation: canCreateDirect || hasFormalConversation,
      hasPendingGreeting: hasPendingGreeting,
      hasFormalConversation: hasFormalConversation,
      canStartVoiceCall: !blocked && isMutual,
      canStartVideoCall: !blocked && isMutual,
      isBlocked: isBlocked,
      isBlockedBy: isBlockedBy,
    );
  }

  RelationshipCapabilityDto copyWith({
    String? viewerSubAccountId,
    String? targetSubAccountId,
    String? relationState,
    bool? canFollow,
    bool? canUnfollow,
    bool? canFollowBack,
    bool? canGreet,
    bool? canCreateDirectConversation,
    bool? canSendMessage,
    bool? canOpenConversation,
    bool? hasPendingGreeting,
    bool? hasFormalConversation,
    bool? canStartVoiceCall,
    bool? canStartVideoCall,
    bool? isBlocked,
    bool? isBlockedBy,
  }) {
    return RelationshipCapabilityDto(
      viewerSubAccountId: viewerSubAccountId ?? this.viewerSubAccountId,
      targetSubAccountId: targetSubAccountId ?? this.targetSubAccountId,
      relationState: relationState ?? this.relationState,
      canFollow: canFollow ?? this.canFollow,
      canUnfollow: canUnfollow ?? this.canUnfollow,
      canFollowBack: canFollowBack ?? this.canFollowBack,
      canGreet: canGreet ?? this.canGreet,
      canCreateDirectConversation:
          canCreateDirectConversation ?? this.canCreateDirectConversation,
      canSendMessage: canSendMessage ?? this.canSendMessage,
      canOpenConversation: canOpenConversation ?? this.canOpenConversation,
      hasPendingGreeting: hasPendingGreeting ?? this.hasPendingGreeting,
      hasFormalConversation: hasFormalConversation ?? this.hasFormalConversation,
      canStartVoiceCall: canStartVoiceCall ?? this.canStartVoiceCall,
      canStartVideoCall: canStartVideoCall ?? this.canStartVideoCall,
      isBlocked: isBlocked ?? this.isBlocked,
      isBlockedBy: isBlockedBy ?? this.isBlockedBy,
    );
  }
}

/// 关系能力位 Repository（三层模式）
abstract class RelationshipCapabilityRepository {
  Future<RelationshipCapabilityDto> getCapability(String targetUserId);

  bool get reconcilesCapabilityWithSharedRelationshipState;
}

class MockRelationshipCapabilityRepository
    extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final relationState = UserProfileMockData.relationStateFor(targetUserId);
    return RelationshipCapabilityDto.fromFollowFlags(
      viewerId: ChatMockData.currentUserProfileId,
      targetId: targetUserId,
      isFollowing: UserProfileMockData.viewerFollowsTarget(targetUserId),
      isFollowedBy: UserProfileMockData.targetFollowsViewer(targetUserId),
      isSelf: relationState == MockProfileRelationState.self,
    );
  }
}

class RemoteRelationshipCapabilityRepository
    extends RelationshipCapabilityRepository {
  RemoteRelationshipCapabilityRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
  })  : _httpClient = httpClient ?? CloudHttpClient(),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final path = UserApiMetadata.getRelationshipCapabilityPath(
      subAccountId: targetUserId,
    );
    final uri = Uri.parse('$_baseUrl$path');
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getRelationshipCapability,
      ),
    );
    final body = CloudResponseDecoder.asObject(
      decoded,
      context: UserRequestPageIds.getRelationshipCapability,
    );
    return RelationshipCapabilityDto.fromRelationshipCapabilityWire(
      RelationshipCapabilityWireDto.fromMap(body),
    );
  }
}
