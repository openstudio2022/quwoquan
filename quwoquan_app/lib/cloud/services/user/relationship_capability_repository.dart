import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 关系能力位投影 DTO
/// 对应 GET /user/{userId}/relationship/capability
/// 端侧消费方：用户主页动作矩阵、RTC 门禁、私信/打招呼入口
class RelationshipCapabilityDto {
  const RelationshipCapabilityDto({
    required this.viewerPersonaId,
    required this.targetPersonaId,
    required this.relationState,
    required this.canFollow,
    required this.canUnfollow,
    required this.canFollowBack,
    required this.canGreet,
    required this.canCreateDirectConversation,
    required this.canSendMessage,
    required this.canOpenConversation,
    required this.hasPendingGreeting,
    required this.hasFormalConversation,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
  });

  final String viewerPersonaId;
  final String targetPersonaId;

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

  factory RelationshipCapabilityDto.fromRelationshipCapabilityWire(
    RelationshipCapabilityWireDto w,
  ) {
    return RelationshipCapabilityDto(
      viewerPersonaId: w.viewerPersonaId,
      targetPersonaId: w.targetPersonaId,
      relationState: _requiredWireValue(w.relationState, 'relationState'),
      canFollow: _requiredWireValue(w.canFollow, 'canFollow'),
      canUnfollow: _requiredWireValue(w.canUnfollow, 'canUnfollow'),
      canFollowBack: _requiredWireValue(w.canFollowBack, 'canFollowBack'),
      canGreet: w.canGreet,
      canCreateDirectConversation: w.canCreateDirectConversation,
      canSendMessage: w.canSendMessage,
      canOpenConversation: _requiredWireValue(
        w.canOpenConversation,
        'canOpenConversation',
      ),
      hasPendingGreeting: w.hasPendingGreeting,
      hasFormalConversation: w.hasFormalConversation,
      canStartVoiceCall: w.canStartVoiceCall,
      canStartVideoCall: w.canStartVideoCall,
      isBlocked: w.isBlocked,
      isBlockedBy: w.isBlockedBy,
    );
  }

  factory RelationshipCapabilityDto.fromContract(
    RelationshipCapabilityResult result,
  ) {
    return RelationshipCapabilityDto(
      viewerPersonaId: result.viewerPersonaId,
      targetPersonaId: result.targetPersonaId,
      relationState: result.relationState,
      canFollow: result.canFollow,
      canUnfollow: result.canUnfollow,
      canFollowBack: result.canFollowBack,
      canGreet: result.canGreet,
      canCreateDirectConversation: result.canCreateDirectConversation,
      canSendMessage: result.canSendMessage,
      canOpenConversation: result.canOpenConversation,
      hasPendingGreeting: result.hasPendingGreeting,
      hasFormalConversation: result.hasFormalConversation,
      canStartVoiceCall: result.canStartVoiceCall,
      canStartVideoCall: result.canStartVideoCall,
      isBlocked: result.isBlocked,
      isBlockedBy: result.isBlockedBy,
    );
  }

  factory RelationshipCapabilityDto.fromMap(Map<String, dynamic> map) {
    _requireCanonicalCapabilityMap(map);
    return RelationshipCapabilityDto.fromRelationshipCapabilityWire(
      RelationshipCapabilityWireDto.fromMap(map),
    );
  }

  Map<String, Object?> toWireMap() => <String, Object?>{
    'viewerPersonaId': viewerPersonaId,
    'targetPersonaId': targetPersonaId,
    'relationState': relationState,
    'canFollow': canFollow,
    'canUnfollow': canUnfollow,
    'canFollowBack': canFollowBack,
    'canGreet': canGreet,
    'canOpenConversation': canOpenConversation,
    'canCreateDirectConversation': canCreateDirectConversation,
    'canSendMessage': canSendMessage,
    'hasPendingGreeting': hasPendingGreeting,
    'hasFormalConversation': hasFormalConversation,
    'canStartVoiceCall': canStartVoiceCall,
    'canStartVideoCall': canStartVideoCall,
    'isBlocked': isBlocked,
    'isBlockedBy': isBlockedBy,
  };
}

T _requiredWireValue<T>(T? value, String field) {
  if (value == null) {
    throw FormatException('RelationshipCapabilityWire.$field is required');
  }
  return value;
}

void _requireCanonicalCapabilityMap(Map<String, dynamic> map) {
  for (final field in const <String>[
    'viewerPersonaId',
    'targetPersonaId',
    'relationState',
  ]) {
    if (map[field] is! String) {
      throw FormatException('RelationshipCapabilityWire.$field is required');
    }
  }
  for (final field in const <String>[
    'canFollow',
    'canUnfollow',
    'canFollowBack',
    'canGreet',
    'canOpenConversation',
    'canCreateDirectConversation',
    'canSendMessage',
    'hasPendingGreeting',
    'hasFormalConversation',
    'canStartVoiceCall',
    'canStartVideoCall',
    'isBlocked',
    'isBlockedBy',
  ]) {
    if (map[field] is! bool) {
      throw FormatException('RelationshipCapabilityWire.$field is required');
    }
  }
}

/// 关系能力位 Repository（三层模式）
abstract class RelationshipCapabilityRepository {
  Future<RelationshipCapabilityDto> getCapability(String targetUserId);

  bool get reconcilesCapabilityWithSharedRelationshipState;
}

class RemoteRelationshipCapabilityRepository
    implements RelationshipCapabilityRepository {
  const RemoteRelationshipCapabilityRepository({required this.query});

  final RelationshipCapabilityQuery query;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final result = await query.getRelationshipCapability(
      GetRelationshipCapabilityQuery(targetPersonaId: targetUserId),
    );
    return RelationshipCapabilityDto.fromContract(result);
  }
}
