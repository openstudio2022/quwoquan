import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/mock/prototype_mock_data.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';

ChatInboxDto _chatInboxFromPrototypeMap(Map<String, dynamic> m) {
  final base = Map<String, dynamic>.from(m);
  if (m['hasMention'] == true) {
    base['mentionUnreadCount'] =
        (base['mentionUnreadCount'] as num?)?.toInt() ?? 1;
  }
  return ChatInboxDto.fromMap(base);
}

/// 将 [PrototypeMockData] 中的会话 map 转为 [ChatInboxDto]。
List<ChatInboxDto> decodeChatInboxRows(List<Map<String, dynamic>> rows) {
  return rows.map(_chatInboxFromPrototypeMap).toList(growable: false);
}

ChatContactTabCircleRowDto _contactCircleFromMap(Map<String, dynamic> m) {
  return ChatContactTabCircleRowDto.fromMap(<String, dynamic>{
    'id': m['id'],
    'circleId': m['id'],
    'displayName': m['name'] ?? m['displayName'] ?? '',
    'avatarUrl': m['avatar'] ?? m['avatarUrl'] ?? '',
    'subtitle': m['memberCount']?.toString() ?? '',
  });
}

ChatContactTabFunGroupRowDto _contactGroupFromMap(Map<String, dynamic> m) {
  return ChatContactTabFunGroupRowDto.fromMap(<String, dynamic>{
    'id': m['id'],
    'conversationId': m['id'],
    'displayName': m['name'] ?? m['displayName'] ?? '',
    'avatarUrl': m['avatar'] ?? m['avatarUrl'] ?? '',
    'subtitle': m['memberCount']?.toString() ?? '',
  });
}

List<ChatContactTabCircleRowDto> decodeChatContactCircles(
  List<Map<String, dynamic>> rows,
) {
  return rows.map((e) => _contactCircleFromMap(e)).toList(growable: false);
}

List<ChatContactTabFunGroupRowDto> decodeChatContactGroups(
  List<Map<String, dynamic>> rows,
) {
  return rows.map((e) => _contactGroupFromMap(e)).toList(growable: false);
}

List<ChatMessageDto> decodeChatMessages(List<Map<String, dynamic>> rows) {
  return rows
      .map((e) => ChatMessageDto.fromMap(Map<String, dynamic>.from(e)))
      .toList(growable: false);
}

CirclePagePrototypeInfo decodeCirclePageInfo(Map<String, dynamic> m) {
  final statsRaw = m['stats'];
  Map<String, dynamic> statsMap = const {};
  if (statsRaw is Map) {
    statsMap = Map<String, dynamic>.from(statsRaw);
  }
  return CirclePagePrototypeInfo(
    name: m['name']?.toString() ?? '',
    id: m['id']?.toString() ?? '',
    avatar: m['avatar']?.toString() ?? '',
    cover: m['cover']?.toString() ?? '',
    desc: m['desc']?.toString() ?? '',
    stats: CirclePrototypeStats(
      members: statsMap['members']?.toString() ?? '',
      groups: statsMap['groups']?.toString() ?? '',
      fans: statsMap['fans']?.toString() ?? '',
      likes: statsMap['likes']?.toString() ?? '',
    ),
    hasNewMessages: m['hasNewMessages'] as bool? ?? false,
  );
}

Map<String, CircleCategoryTabConfigDto> decodeCirclesCategoryConfig(
  Map<String, Map<String, dynamic>> raw,
) {
  return raw.map(
    (k, v) => MapEntry(k, CircleCategoryTabConfigDto.fromMap(v)),
  );
}

List<CircleDto> decodeCircleDtos(List<Map<String, dynamic>> rows) {
  return rows
      .map((e) => CircleDto.fromMap(Map<String, dynamic>.from(e)))
      .toList(growable: false);
}

List<CircleActivityPrototypeRow> decodeCircleActivities(
  List<Map<String, dynamic>> rows,
) {
  return rows
      .map(
        (m) => CircleActivityPrototypeRow(
          id: m['id']?.toString() ?? '',
          type: m['type']?.toString() ?? '',
          title: m['title']?.toString() ?? '',
          status: m['status']?.toString() ?? '',
          circleId: m['circleId']?.toString() ?? '',
          circleName: m['circleName']?.toString() ?? '',
          participants: (m['participants'] as num?)?.toInt() ?? 0,
          image: m['image']?.toString() ?? '',
        ),
      )
      .toList(growable: false);
}

Object? _objectifyValue(dynamic v) {
  if (v == null) return null;
  if (v is String || v is num || v is bool) return v;
  if (v is List) {
    return v.map(_objectifyValue).toList(growable: false);
  }
  if (v is Map) {
    return v.map(
      (k, val) => MapEntry(k.toString(), _objectifyValue(val)),
    );
  }
  return v.toString();
}

HelperReadSummaryPrototype decodeHelperReadSummary(Map<String, dynamic> m) {
  final dimsRaw = m['dimensions'];
  final dimensions = <HelperReadDimensionPrototype>[];
  if (dimsRaw is List) {
    for (final d in dimsRaw) {
      if (d is! Map) continue;
      final dm = Map<String, dynamic>.from(d);
      final itemsRaw = dm['items'];
      final items = <HelperReadFactItemPrototype>[];
      if (itemsRaw is List) {
        for (final it in itemsRaw) {
          if (it is Map) {
            final im = Map<Object?, Object?>.from(it);
            items.add(
              HelperReadFactItemPrototype(
                raw: im.map(
                  (k, val) =>
                      MapEntry(k.toString(), _objectifyValue(val)),
                ),
              ),
            );
          }
        }
      }
      dimensions.add(
        HelperReadDimensionPrototype(
          dimensionKey: dm['dimensionKey']?.toString() ?? '',
          title: dm['title']?.toString() ?? '',
          items: items,
        ),
      );
    }
  }
  return HelperReadSummaryPrototype(
    oneLiner: m['oneLiner']?.toString() ?? '',
    dimensions: dimensions,
  );
}

List<AssistantPrototypeMemoryRow> decodeAssistantMemories(
  List<Map<String, dynamic>> rows,
) {
  return rows
      .map(
        (m) => AssistantPrototypeMemoryRow(
          memoryKey: m['id']?.toString() ?? '',
          title: m['title']?.toString() ?? '',
          kind: m['type']?.toString(),
          dateLabel: m['date']?.toString(),
          iconEmoji: m['icon']?.toString(),
        ),
      )
      .toList(growable: false);
}

List<AssistantPrototypeTaskRow> decodeAssistantTasks(
  List<Map<String, dynamic>> rows,
) {
  return rows
      .map(
        (m) => AssistantPrototypeTaskRow(
          taskKey: m['id']?.toString() ?? '',
          title: m['title']?.toString() ?? '',
          time: m['time']?.toString(),
          status: m['status']?.toString() ?? 'pending',
          category: m['category']?.toString(),
        ),
      )
      .toList(growable: false);
}

List<AssistantPrototypeSkillRow> decodeAssistantSkills(
  List<Map<String, dynamic>> rows,
) {
  return rows
      .map(
        (m) => AssistantPrototypeSkillRow(
          skillId: m['id']?.toString() ?? '',
          name: m['name']?.toString() ?? '',
          description: m['desc']?.toString(),
          active: m['active'] as bool? ?? false,
        ),
      )
      .toList(growable: false);
}

/// 从 [PrototypeMockData] 加载强类型聊天/圈子/助理原型（单处聚合，供 [MockAppContentRepository] 使用）。
class AppContentPrototypeBundle {
  AppContentPrototypeBundle._({
    required this.chatMockConversations,
    required this.chatMockConversationsAtMe,
    required this.chatEncryptedConversations,
    required this.chatAssistantConversation,
    required this.chatMockContactCircles,
    required this.chatMockContactGroups,
    required this.chatMockContacts,
    required this.assistantMemoryData,
    required this.assistantTasksData,
    required this.assistantSkillsData,
    required this.helperReadSummary,
    required this.circlePageCircleInfo,
    required this.circlesCategoryConfig,
    required this.circlesMockActivities,
    required this.circlesMockCircles,
  });

  static final AppContentPrototypeBundle instance = AppContentPrototypeBundle._(
    chatMockConversations: decodeChatInboxRows(
      PrototypeMockData.chatMockConversations,
    ),
    chatMockConversationsAtMe: decodeChatInboxRows(
      PrototypeMockData.chatMockConversationsAtMe,
    ),
    chatEncryptedConversations: decodeChatInboxRows(
      PrototypeMockData.chatEncryptedConversations,
    ),
    chatAssistantConversation: _chatInboxFromPrototypeMap(
      PrototypeMockData.chatAssistantConversation,
    ),
    chatMockContactCircles: decodeChatContactCircles(
      PrototypeMockData.chatMockContactCircles,
    ),
    chatMockContactGroups: decodeChatContactGroups(
      PrototypeMockData.chatMockContactGroups,
    ),
    chatMockContacts: PrototypeMockData.chatMockContacts
        .map((e) => ChatContactRowDto.fromMap(Map<String, dynamic>.from(e)))
        .toList(growable: false),
    assistantMemoryData: decodeAssistantMemories(
      PrototypeMockData.assistantMemoryData,
    ),
    assistantTasksData: decodeAssistantTasks(
      PrototypeMockData.assistantTasksData,
    ),
    assistantSkillsData: decodeAssistantSkills(
      PrototypeMockData.assistantSkillsData,
    ),
    helperReadSummary: decodeHelperReadSummary(
      PrototypeMockData.helperReadSummary,
    ),
    circlePageCircleInfo: decodeCirclePageInfo(
      PrototypeMockData.circlePageCircleInfo,
    ),
    circlesCategoryConfig: decodeCirclesCategoryConfig(
      PrototypeMockData.circlesCategoryConfig,
    ),
    circlesMockActivities: decodeCircleActivities(
      PrototypeMockData.circlesMockActivities,
    ),
    circlesMockCircles: decodeCircleDtos(
      PrototypeMockData.circlesMockCircles,
    ),
  );

  final List<ChatInboxDto> chatMockConversations;
  final List<ChatInboxDto> chatMockConversationsAtMe;
  final List<ChatInboxDto> chatEncryptedConversations;
  final ChatInboxDto chatAssistantConversation;
  final List<ChatContactTabCircleRowDto> chatMockContactCircles;
  final List<ChatContactTabFunGroupRowDto> chatMockContactGroups;
  final List<ChatContactRowDto> chatMockContacts;
  final List<AssistantPrototypeMemoryRow> assistantMemoryData;
  final List<AssistantPrototypeTaskRow> assistantTasksData;
  final List<AssistantPrototypeSkillRow> assistantSkillsData;
  final HelperReadSummaryPrototype helperReadSummary;
  final CirclePagePrototypeInfo circlePageCircleInfo;
  final Map<String, CircleCategoryTabConfigDto> circlesCategoryConfig;
  final List<CircleActivityPrototypeRow> circlesMockActivities;
  final List<CircleDto> circlesMockCircles;

  List<ChatMessageDto> chatMessagesFor(String conversationId) {
    return decodeChatMessages(
      PrototypeMockData.chatMessagesFor(conversationId),
    );
  }
}
