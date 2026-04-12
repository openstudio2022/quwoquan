import 'dart:convert';

import 'package:http/http.dart' as http;
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
/// 端侧消费方：用户主页五态按钮矩阵、RTC 门禁
class RelationshipCapabilityDto {
  RelationshipCapabilityDto({
    required this.viewerSubAccountId,
    required this.targetSubAccountId,
    String? relationState,
    String? relationTier,
    bool? canFollow,
    bool? canUnfollow,
    bool? canMessage,
    bool? canFollowBack,
    required this.canGreet,
    required this.canOpenConversation,
    required this.canAddSameInterest,
    required this.canSetCloseFriend,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
  }) : relationState = _normalizeRelationState(
         relationState ?? relationTier ?? 'not_following',
       ),
       canFollow =
           canFollow ??
           _defaultCanFollow(
             _normalizeRelationState(
               relationState ?? relationTier ?? 'not_following',
             ),
           ),
       canUnfollow =
           canUnfollow ??
           _defaultCanUnfollow(
             _normalizeRelationState(
               relationState ?? relationTier ?? 'not_following',
             ),
           ),
       canMessage =
           canMessage ??
           _defaultCanMessage(
             _normalizeRelationState(
               relationState ?? relationTier ?? 'not_following',
             ),
           ),
       canFollowBack =
           canFollowBack ??
           _defaultCanFollowBack(
             _normalizeRelationState(
               relationState ?? relationTier ?? 'not_following',
             ),
           ),
       relationTier =
           relationTier ??
           _relationTierFromNormalizedState(
             _normalizeRelationState(
               relationState ?? relationTier ?? 'not_following',
             ),
           );

  final String viewerSubAccountId;
  final String targetSubAccountId;

  /// 统一关系态：self | not_following | following | followed_by | mutual
  final String relationState;

  final bool canFollow;
  final bool canUnfollow;
  final bool canMessage;
  final bool canFollowBack;

  /// 兼容旧契约：self | none | following_only | same_interest | close_friend
  final String relationTier;

  final bool canGreet;
  final bool canOpenConversation;
  final bool canAddSameInterest;
  final bool canSetCloseFriend;
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
  bool get isSameInterest =>
      relationTier == 'same_interest' || relationTier == 'close_friend';
  bool get isCloseFriend => relationTier == 'close_friend';
  bool get isFollowingOnly => relationTier == 'following_only';
  bool get isStranger => relationTier == 'none';

  static String _normalizeRelationState(String raw) {
    switch (raw) {
      case 'self':
        return 'self';
      case 'mutual':
      case 'same_interest':
      case 'close_friend':
        return 'mutual';
      case 'following':
      case 'following_only':
        return 'following';
      case 'followed_by':
        return 'followed_by';
      case 'none':
      case 'not_following':
      default:
        return 'not_following';
    }
  }

  static String _relationTierFromNormalizedState(String relationState) {
    switch (relationState) {
      case 'self':
        return 'self';
      case 'mutual':
        return 'same_interest';
      case 'following':
        return 'following_only';
      case 'followed_by':
      case 'not_following':
      default:
        return 'none';
    }
  }

  static bool _defaultCanFollow(String relationState) {
    return relationState == 'not_following' || relationState == 'followed_by';
  }

  static bool _defaultCanUnfollow(String relationState) {
    return relationState == 'following' || relationState == 'mutual';
  }

  static bool _defaultCanMessage(String relationState) {
    return relationState != 'self';
  }

  static bool _defaultCanFollowBack(String relationState) {
    return relationState == 'followed_by';
  }

  factory RelationshipCapabilityDto.fromRelationshipCapabilityWire(
    RelationshipCapabilityWireDto w,
  ) {
    return RelationshipCapabilityDto(
      viewerSubAccountId: w.viewerProfileSubjectId,
      targetSubAccountId: w.targetProfileSubjectId,
      relationState: w.relationState,
      relationTier: w.relationTier,
      canFollow: w.canFollow,
      canUnfollow: w.canUnfollow,
      canMessage: w.canMessage,
      canFollowBack: w.canFollowBack,
      canGreet: w.canGreet,
      canOpenConversation: w.canOpenConversation ?? w.canMessage ?? false,
      canAddSameInterest: w.canAddSameInterest,
      canSetCloseFriend: w.canSetCloseFriend,
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
    bool closeFriend = false,
    bool isSelf = false,
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
    return RelationshipCapabilityDto(
      viewerSubAccountId: viewerId,
      targetSubAccountId: targetId,
      relationState: relationState,
      relationTier: isSelf
          ? 'self'
          : isMutual
          ? (closeFriend ? 'close_friend' : 'same_interest')
          : isFollowing
          ? 'following_only'
          : 'none',
      canGreet: !isSelf && isFollowing && !isMutual,
      canOpenConversation: isMutual,
      canAddSameInterest: isMutual,
      canSetCloseFriend: isMutual,
      canStartVoiceCall: isMutual,
      canStartVideoCall: isMutual,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

/// 关系能力位 Repository（三层模式）
///
/// 对应云侧路由（contracts/metadata/user/follow_edge/service.yaml）：
///   GET /v1/user/{userId}/relationship/capability
abstract class RelationshipCapabilityRepository {
  Future<RelationshipCapabilityDto> getCapability(String targetUserId);

  /// 是否与全局关系态对齐能力位（内嵌目录为 true；云侧以接口为准）。
  bool get reconcilesCapabilityWithSharedRelationshipState;
}

/// Mock 实现：返回本地推导的能力位（用于本地开发和测试）
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

/// Remote 实现：调用云侧 API
class RemoteRelationshipCapabilityRepository
    extends RelationshipCapabilityRepository {
  RemoteRelationshipCapabilityRepository({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final path = UserApiMetadata.getRelationshipCapabilityPath(
      profileSubjectId: targetUserId,
    );
    final uri = Uri.parse('$_baseUrl$path');
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getRelationshipCapability,
      ),
    );
    if (resp.statusCode == 200) {
      final body = CloudResponseDecoder.asObject(
        jsonDecode(resp.body),
        context: UserRequestPageIds.getRelationshipCapability,
      );
      return RelationshipCapabilityDto.fromRelationshipCapabilityWire(
        RelationshipCapabilityWireDto.fromMap(body),
      );
    }
    throw Exception(
      'GetRelationshipCapability failed: ${resp.statusCode} ${resp.body}',
    );
  }
}
