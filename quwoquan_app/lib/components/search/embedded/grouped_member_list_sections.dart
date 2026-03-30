import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 一组群成员（展示用分组头 + 成员列表）。
class MemberListSectionData {
  const MemberListSectionData({
    required this.header,
    required this.members,
  });

  final String header;
  final List<Map<String, dynamic>> members;
}

String memberDisplayName(Map<String, dynamic> m) =>
    (m['displayName'] as String?)?.trim().isNotEmpty == true
        ? (m['displayName'] as String).trim()
        : (m['name'] as String?)?.trim() ?? '';

/// 群成员 DTO 分组（群主一节 + 按展示名首字母分桶）。
class MemberDtoListSectionData {
  const MemberDtoListSectionData({
    required this.header,
    required this.members,
  });

  final String header;
  final List<ChatConversationMemberDto> members;
}

String memberDtoDisplayName(ChatConversationMemberDto m) =>
    m.displayName.trim().isNotEmpty ? m.displayName.trim() : '';

List<MemberDtoListSectionData> buildGroupedMemberDtoSections(
  List<ChatConversationMemberDto> members,
) {
  final owners = members.where((m) => m.role == 'owner').toList();
  final rest = members.where((m) => m.role != 'owner').toList();
  rest.sort(
    (a, b) => memberDtoDisplayName(a).compareTo(memberDtoDisplayName(b)),
  );

  final buckets = <String, List<ChatConversationMemberDto>>{};
  for (final m in rest) {
    final key = _bucketKeyForName(memberDtoDisplayName(m));
    buckets.putIfAbsent(key, () => <ChatConversationMemberDto>[]).add(m);
  }

  final keys = buckets.keys.toList()..sort(_compareBucketKeys);
  final out = <MemberDtoListSectionData>[];
  if (owners.isNotEmpty) {
    out.add(
      MemberDtoListSectionData(header: UITextConstants.owner, members: owners),
    );
  }
  for (final k in keys) {
    final list = buckets[k];
    if (list != null && list.isNotEmpty) {
      out.add(MemberDtoListSectionData(header: k, members: list));
    }
  }
  return out;
}

/// 群主一节 + 按展示名首字母分桶（A–Z，其它为 `#`）。
List<MemberListSectionData> buildGroupedMemberSections(
  List<Map<String, dynamic>> members,
) {
  final owners = members.where((m) => m['role'] == 'owner').toList();
  final rest = members.where((m) => m['role'] != 'owner').toList();
  rest.sort(
    (a, b) => memberDisplayName(a).compareTo(memberDisplayName(b)),
  );

  final buckets = <String, List<Map<String, dynamic>>>{};
  for (final m in rest) {
    final key = _bucketKeyForName(memberDisplayName(m));
    buckets.putIfAbsent(key, () => <Map<String, dynamic>>[]).add(m);
  }

  final keys = buckets.keys.toList()..sort(_compareBucketKeys);
  final out = <MemberListSectionData>[];
  if (owners.isNotEmpty) {
    out.add(
      MemberListSectionData(header: UITextConstants.owner, members: owners),
    );
  }
  for (final k in keys) {
    final list = buckets[k];
    if (list != null && list.isNotEmpty) {
      out.add(MemberListSectionData(header: k, members: list));
    }
  }
  return out;
}

String _bucketKeyForName(String name) {
  if (name.isEmpty) return '#';
  final first = name.substring(0, 1);
  final upper = first.toUpperCase();
  if (upper.isEmpty) return '#';
  final u = upper.codeUnitAt(0);
  if (u >= 0x41 && u <= 0x5A) return upper;
  return '#';
}

int _compareBucketKeys(String a, String b) {
  if (a == '#') return 1;
  if (b == '#') return -1;
  return a.compareTo(b);
}

/// 分组标题（群主 / A / B / …）。
class MemberListSectionHeader extends StatelessWidget {
  const MemberListSectionHeader({
    super.key,
    required this.isDark,
    required this.title,
  });

  final bool isDark;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupSm,
        AppSpacing.containerMd,
        AppSpacing.xs,
      ),
      child: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.medium,
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.foregroundSecondary,
          ),
        ),
      ),
    );
  }
}
