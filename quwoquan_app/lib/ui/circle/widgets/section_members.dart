import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';
import 'package:quwoquan_app/ui/circle/services/circle_stats_row_wire.dart';

/// 圈子成员板块：展示成员摘要列表（含独立 loading/error 状态）。
class SectionMembers extends ConsumerStatefulWidget {
  const SectionMembers({
    super.key,
    required this.circleId,
    required this.isDark,
  });

  final String circleId;
  final bool isDark;

  @override
  ConsumerState<SectionMembers> createState() => _SectionMembersState();
}

class _SectionMembersState extends ConsumerState<SectionMembers> {
  bool _isLoading = true;
  UiErrorSemantic? _errorSemantic;
  List<CircleStatsMemberRowViewData> _members = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadMembers());
  }

  Future<void> _loadMembers() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
    });
    try {
      final repo = ref.read(circleRepositoryProvider);
      final roster = await repo.listMembers(widget.circleId, limit: 6);
      if (!mounted) {
        return;
      }
      setState(() {
        _members = roster
            .map(circleStatsMemberRowFromRosterItem)
            .toList(growable: false);
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.section,
        );
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_errorSemantic != null) {
      return AppSectionErrorCard(
        semantic: _errorSemantic!,
        margin: EdgeInsets.zero,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadMembers();
          }
        },
      );
    }
    if (_members.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.noData,
          style: TextStyle(
            fontSize: AppTypography.base,
            color: AppColorsFunctional.getColor(
              widget.isDark,
              ColorType.foregroundSecondary,
            ),
          ),
        ),
      );
    }

    final fgPrimary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );

    return Column(
      children: _members
          .map(
            (member) => Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: borderColor.withValues(alpha: 0.08),
                    width: AppSpacing.hairline,
                  ),
                ),
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: AppSpacing.md,
                    backgroundImage: member.avatarUrl.trim().isEmpty
                        ? null
                        : NetworkImage(member.avatarUrl),
                    onBackgroundImageError: (_, _) {},
                    child: member.avatarUrl.trim().isEmpty
                        ? Text(
                            member.name.isEmpty
                                ? '?'
                                : member.name.substring(0, 1),
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              fontWeight: AppTypography.semiBold,
                              color: fgPrimary,
                            ),
                          )
                        : null,
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          member.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          '${member.worksCountLabel} 创作 · ${member.likesCountLabel} 获赞',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}
