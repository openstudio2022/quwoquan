import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

export 'package:quwoquan_app/cloud/services/app_content/app_content_repository_provider.dart';

enum AppDataSourceMode { mock, remote }

class AppDataSourceModeNotifier extends Notifier<AppDataSourceMode> {
  @override
  AppDataSourceMode build() {
    const v = String.fromEnvironment('APP_DATA_SOURCE', defaultValue: '');
    if (v == 'remote') {
      return AppDataSourceMode.remote;
    }
    if (v == 'mock') {
      return AppDataSourceMode.mock;
    }
    return kReleaseMode ? AppDataSourceMode.remote : AppDataSourceMode.mock;
  }

  void setMode(AppDataSourceMode mode) {
    state = mode;
  }
}

final appDataSourceModeProvider =
    NotifierProvider<AppDataSourceModeNotifier, AppDataSourceMode>(
  AppDataSourceModeNotifier.new,
);

abstract class AppContentRepository {
  List<Map<String, dynamic>> get discoveryMomentData;
  List<Map<String, dynamic>> get discoveryPhotoData;
  List<Map<String, dynamic>> get discoveryArticleData;
  List<Map<String, dynamic>> get discoveryVideoData;
  Map<String, dynamic>? articleById(String id);

  /// 发现 Feed 原型数据中按 postId 定位单行 Map（分享模板圈名/tags 等扩展字段；非 codegen DTO）。
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId);

  List<Map<String, dynamic>> get chatMockConversations;
  List<Map<String, dynamic>> get chatMockConversationsAtMe;
  List<Map<String, dynamic>> get chatEncryptedConversations;
  Map<String, dynamic> get chatAssistantConversation;
  List<Map<String, dynamic>> get chatMockContactCircles;
  List<Map<String, dynamic>> get chatMockContacts;
  List<Map<String, dynamic>> get chatMockContactGroups;
  List<Map<String, dynamic>> chatMessagesFor(String conversationId);

  List<Map<String, dynamic>> get assistantMemoryData;
  List<Map<String, dynamic>> get assistantTasksData;
  List<Map<String, dynamic>> get assistantSkillsData;

  /// 帮读摘要：一句话综述 + 分维度展开事实。格式见 PrototypeMockData.helperReadSummary。
  Map<String, dynamic> get helperReadSummary;

  Map<String, dynamic> get circlePageCircleInfo;
  Map<String, Map<String, dynamic>> get circlesCategoryConfig;
  List<Map<String, dynamic>> get circlesMockActivities;
  List<Map<String, dynamic>> get circlesMockCircles;
}

/// 在发现区四类 mock 聚合中按帖子 id 查找原始 wire 行（仅 parse/原型边界用）。
Map<String, dynamic>? lookupDiscoveryFeedWireRow(
  AppContentRepository repo,
  String postId,
) {
  if (postId.isEmpty) return null;
  final all = <Map<String, dynamic>>[
    ...repo.discoveryPhotoData,
    ...repo.discoveryVideoData,
    ...repo.discoveryArticleData,
    ...repo.discoveryMomentData,
  ];
  for (final item in all) {
    final itemId =
        item['postId']?.toString() ??
        item['_id']?.toString() ??
        item['id']?.toString() ??
        '';
    if (itemId == postId) {
      return item;
    }
  }
  return null;
}

/// 在四类发现 mock 聚合中按帖子 id 解析为 [PostBaseDto]（无则 null）。
///
/// 与 [lookupDiscoveryFeedWireRow] 成对使用：优先消费本函数的强类型结果，仅在需要 wire 扩展字段时回退 map。
PostBaseDto? lookupDiscoveryPostBaseDto(AppContentRepository repo, String postId) {
  final row = lookupDiscoveryFeedWireRow(repo, postId);
  if (row == null || row.isEmpty) {
    return null;
  }
  return postBaseDtoFromMap(row);
}

class RemoteAppContentRepository implements AppContentRepository {
  RemoteAppContentRepository();

  static final List<Map<String, dynamic>> _empty =
      List<Map<String, dynamic>>.unmodifiable(<Map<String, dynamic>>[]);

  @override
  List<Map<String, dynamic>> get discoveryMomentData => _empty;

  @override
  List<Map<String, dynamic>> get discoveryPhotoData => _empty;

  @override
  List<Map<String, dynamic>> get discoveryArticleData => _empty;

  @override
  List<Map<String, dynamic>> get discoveryVideoData => _empty;

  @override
  Map<String, dynamic>? articleById(String id) => null;

  @override
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId) => null;

  @override
  List<Map<String, dynamic>> get chatMockConversations => _empty;

  @override
  List<Map<String, dynamic>> get chatMockConversationsAtMe => _empty;

  @override
  List<Map<String, dynamic>> get chatEncryptedConversations => _empty;

  @override
  Map<String, dynamic> get chatAssistantConversation => const {};

  @override
  List<Map<String, dynamic>> get chatMockContactCircles => _empty;

  @override
  List<Map<String, dynamic>> get chatMockContacts => _empty;

  @override
  List<Map<String, dynamic>> get chatMockContactGroups => _empty;

  @override
  List<Map<String, dynamic>> chatMessagesFor(String conversationId) => _empty;

  @override
  List<Map<String, dynamic>> get assistantMemoryData => _empty;

  @override
  List<Map<String, dynamic>> get assistantTasksData => _empty;

  @override
  List<Map<String, dynamic>> get assistantSkillsData => _empty;

  @override
  Map<String, dynamic> get helperReadSummary => const {};

  @override
  Map<String, dynamic> get circlePageCircleInfo => const {};

  @override
  Map<String, Map<String, dynamic>> get circlesCategoryConfig => const {
    'all': {'label': '推荐'},
  };

  @override
  List<Map<String, dynamic>> get circlesMockActivities => _empty;

  @override
  List<Map<String, dynamic>> get circlesMockCircles => _empty;
}
