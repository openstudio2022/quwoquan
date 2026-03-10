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
  const RelationshipCapabilityDto({
    required this.viewerSubAccountId,
    required this.targetSubAccountId,
    required this.relationTier,
    required this.canGreet,
    required this.canOpenConversation,
    required this.canAddSameInterest,
    required this.canSetCloseFriend,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
  });

  final String viewerSubAccountId;
  final String targetSubAccountId;

  /// 'none' | 'following_only' | 'same_interest' | 'close_friend' | 'self'
  final String relationTier;

  final bool canGreet;
  final bool canOpenConversation;
  final bool canAddSameInterest;
  final bool canSetCloseFriend;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;
  final bool isBlocked;
  final bool isBlockedBy;

  bool get isSelf => relationTier == 'self';
  bool get isSameInterest =>
      relationTier == 'same_interest' || relationTier == 'close_friend';
  bool get isCloseFriend => relationTier == 'close_friend';
  bool get isFollowingOnly => relationTier == 'following_only';
  bool get isStranger => relationTier == 'none';

  factory RelationshipCapabilityDto.fromMap(Map<String, dynamic> map) {
    return RelationshipCapabilityDto(
      viewerSubAccountId:
          (map['viewerSubAccountId'] as String?) ?? '',
      targetSubAccountId:
          (map['targetSubAccountId'] as String?) ?? '',
      relationTier: (map['relationTier'] as String?) ?? 'none',
      canGreet: (map['canGreet'] as bool?) ?? false,
      canOpenConversation: (map['canOpenConversation'] as bool?) ?? false,
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
    final tier = isSelf
        ? 'self'
        : (closeFriend && isMutual)
            ? 'close_friend'
            : isMutual
                ? 'same_interest'
                : isFollowing
                    ? 'following_only'
                    : 'none';
    return RelationshipCapabilityDto(
      viewerSubAccountId: viewerId,
      targetSubAccountId: targetId,
      relationTier: tier,
      canGreet: !isSelf && !isMutual && isFollowing,
      canOpenConversation: isMutual || closeFriend,
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
      'relationTier': 'same_interest',
      'canGreet': false,
      'canOpenConversation': true,
      'canAddSameInterest': true,
      'canSetCloseFriend': true,
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
