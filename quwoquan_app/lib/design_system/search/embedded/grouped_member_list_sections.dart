import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 群成员 DTO 分组（群主一节 + 按展示名首字母分桶）。
class MemberDtoListSectionData {
  const MemberDtoListSectionData({required this.header, required this.members});

  final String header;
  final List<ConversationMemberListRow> members;
}

String memberDtoDisplayName(ConversationMemberListRow m) =>
    m.displayName.trim().isNotEmpty ? m.displayName.trim() : '';

List<MemberDtoListSectionData> buildGroupedMemberDtoSections(
  List<ConversationMemberListRow> members,
) {
  final owners = members.where((m) => m.role == 'owner').toList();
  final rest = members.where((m) => m.role != 'owner').toList();
  rest.sort(
    (a, b) => memberDtoDisplayName(a).compareTo(memberDtoDisplayName(b)),
  );

  final buckets = <String, List<ConversationMemberListRow>>{};
  for (final m in rest) {
    final key = _bucketKeyForName(memberDtoDisplayName(m));
    buckets.putIfAbsent(key, () => <ConversationMemberListRow>[]).add(m);
  }

  final keys = buckets.keys.toList()..sort(_compareBucketKeys);
  final out = <MemberDtoListSectionData>[];
  if (owners.isNotEmpty) {
    out.add(MemberDtoListSectionData(header: ChatText.owner, members: owners));
  }
  for (final k in keys) {
    final list = buckets[k];
    if (list != null && list.isNotEmpty) {
      out.add(MemberDtoListSectionData(header: k, members: list));
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
