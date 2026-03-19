import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
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
           _legacyRelationTier(
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

  static String _legacyRelationTier(String relationState) {
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

  factory RelationshipCapabilityDto.fromMap(Map<String, dynamic> map) {
    final relationState = map['relationState'] as String?;
    final hasCanMessage = map.containsKey('canMessage');
    return RelationshipCapabilityDto(
      viewerSubAccountId:
          (map['viewerProfileSubjectId'] as String?) ??
          (map['viewerSubAccountId'] as String?) ??
          '',
      targetSubAccountId:
          (map['targetProfileSubjectId'] as String?) ??
          (map['targetSubAccountId'] as String?) ??
          '',
      relationState: relationState,
      relationTier: map['relationTier'] as String?,
      canFollow: map['canFollow'] as bool?,
      canUnfollow: map['canUnfollow'] as bool?,
      canMessage: map['canMessage'] as bool?,
      canFollowBack: map['canFollowBack'] as bool?,
      canGreet: (map['canGreet'] as bool?) ?? false,
      canOpenConversation:
          (map['canOpenConversation'] as bool?) ??
          (hasCanMessage ? (map['canMessage'] as bool?) : null) ??
          false,
      canAddSameInterest: (map['canAddSameInterest'] as bool?) ?? false,
      canSetCloseFriend: (map['canSetCloseFriend'] as bool?) ?? false,
      canStartVoiceCall: (map['canStartVoiceCall'] as bool?) ?? false,
      canStartVideoCall: (map['canStartVideoCall'] as bool?) ?? false,
      isBlocked: (map['isBlocked'] as bool?) ?? false,
      isBlockedBy: (map['isBlockedBy'] as bool?) ?? false,
    );
  }

  /// 本地推导：仅当后端 API 未就绪时使用（从旧版 isFollowing/isFollowedBy 推导）
  factory RelationshipCapabilityDto.fromLegacyRelationship({
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
}

/// Mock 实现：返回本地推导的能力位（用于本地开发和测试）
class MockRelationshipCapabilityRepository
    extends RelationshipCapabilityRepository {
  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'viewerSubAccountId': 'mock_viewer',
      'targetSubAccountId': targetUserId,
      'relationState': 'mutual',
      'relationTier': 'same_interest',
      'canGreet': false,
      'canOpenConversation': true,
      'canAddSameInterest': true,
      'canSetCloseFriend': false,
      'canStartVoiceCall': true,
      'canStartVideoCall': true,
      'isBlocked': false,
      'isBlockedBy': false,
    });
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
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final path = UserApiMetadata.getRelationshipCapabilityPath(
      userId: targetUserId,
    );
    final uri = Uri.parse('$_baseUrl$path');
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getRelationshipCapability,
      ),
    );
    if (resp.statusCode == 200) {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return RelationshipCapabilityDto.fromMap(body);
    }
    throw Exception(
      'GetRelationshipCapability failed: ${resp.statusCode} ${resp.body}',
    );
  }
}
