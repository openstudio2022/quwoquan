import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 通讯录匹配的强类型 App 视图；动态 wire 只在 Repository 边界解码。
class ContactDiscoveryMatchView {
  const ContactDiscoveryMatchView({
    required this.hashedPhone,
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.avatarVersion,
    required this.region,
    required this.relationshipCapability,
  });

  factory ContactDiscoveryMatchView.fromWire(
    ContactDiscoveryMatchResult result,
  ) {
    return ContactDiscoveryMatchView(
      hashedPhone: result.hashedPhone,
      personaId: result.personaId,
      userHandle: result.userHandle,
      displayName: result.displayName,
      avatarUrl: result.avatarUrl,
      avatarVersion: result.avatarVersion,
      region: result.region,
      relationshipCapability: RelationshipCapabilityViewData.fromWire(
        result.relationshipCapability,
      ),
    );
  }

  final String hashedPhone;
  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? region;
  final RelationshipCapabilityViewData relationshipCapability;
}

/// 一次通讯录匹配的结果视图（POST initiate / GET latest 同构）。
///
/// `matches` 是富化投影（[ContactDiscoveryMatchResult]）：回显发起者自己上传的
/// `hashedPhone`（用于把命中映射回本机联系人姓名）+ 精简 profile + viewer 维度的
/// `relationshipCapability`（驱动「添加 / 已添加」按钮）。`matchedPersonaIds` 是
/// 隐私基线（即使富化失败也保证返回）。对方手机号原文端云均不出现。
class ContactDiscoveryResultView {
  const ContactDiscoveryResultView({
    required this.id,
    required this.status,
    required this.matchedPersonaIds,
    required this.matchCount,
    required this.matches,
  });

  final String id;
  final String status;
  final List<String> matchedPersonaIds;
  final int matchCount;
  final List<ContactDiscoveryMatchView> matches;

  static const ContactDiscoveryResultView empty = ContactDiscoveryResultView(
    id: '',
    status: 'completed',
    matchedPersonaIds: <String>[],
    matchCount: 0,
    matches: <ContactDiscoveryMatchView>[],
  );

  factory ContactDiscoveryResultView.fromWire(ContactDiscoveryResult result) {
    return ContactDiscoveryResultView(
      id: result.id,
      status: result.status.wireName,
      matchedPersonaIds: result.matchedPersonaIds,
      matchCount: result.matchCount,
      matches: result.matches
          .map(ContactDiscoveryMatchView.fromWire)
          .toList(growable: false),
    );
  }
}

/// ContactDiscoveryRepository：通讯录批量哈希匹配（窄接口）。
///
/// 端侧上传的 `hashedPhones` 必须由共享 `contact_hash_service`（与服务端
/// `phonematch.Hash` 同算法：规范化 E.164 → +salt → SHA256）派生，匹配只在哈希域完成。
abstract class ContactDiscoveryRepository {
  /// 发起一次通讯录匹配，返回命中结果（含富化 matches）。
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones);

  /// 读取最近一次匹配结果；无记录返回 null。
  Future<ContactDiscoveryResultView?> getLatest();

  /// 关闭/忽略一次匹配记录。
  Future<void> dismiss(String id);
}

class RemoteContactDiscoveryRepository implements ContactDiscoveryRepository {
  const RemoteContactDiscoveryRepository({
    required this.commandWriter,
    required this.query,
  });

  final ContactDiscoveryCommandWriter commandWriter;
  final ContactDiscoveryQuery query;

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    final result = await commandWriter.initiateContactDiscovery(
      InitiateContactDiscoveryCommand(hashedPhones: hashedPhones),
    );
    return ContactDiscoveryResultView.fromWire(result);
  }

  @override
  Future<ContactDiscoveryResultView?> getLatest() async {
    try {
      final result = await query.getLatestContactDiscovery(
        GetLatestContactDiscoveryQuery(),
      );
      if (result.id.isEmpty) {
        return null;
      }
      return ContactDiscoveryResultView.fromWire(result);
    } on CloudException catch (e) {
      // 无历史记录时服务端返回 404，语义上等价于「尚未匹配」。
      if (e.type == CloudErrorType.notFound) {
        return null;
      }
      rethrow;
    }
  }

  @override
  Future<void> dismiss(String id) async {
    await commandWriter.dismissContactDiscovery(
      DismissContactDiscoveryCommand(discoveryId: id),
    );
  }
}
