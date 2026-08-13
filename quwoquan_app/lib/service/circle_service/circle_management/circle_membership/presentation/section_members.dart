import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show circleDetailMembershipQueryProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_list_view_data.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_row_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
      final roster = await ref
          .read(circleDetailMembershipQueryProvider)
          .listMemberships(
            CircleMembershipListQuery(circleId: widget.circleId, limit: 6),
          );
      if (!mounted) {
        return;
      }
      setState(() {
        _members = roster.items
            .map(circleStatsMemberRowFromMembership)
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
      return AppRequestFeedback.section();
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
          CommunityText.noData,
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
          .map((member) {
            final avatarUrl = member.avatarUrl.trim();
            final fallbackAvatar = Center(
              child: Text(
                member.name.isEmpty ? '?' : member.name.substring(0, 1),
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                  color: fgPrimary,
                ),
              ),
            );
            return CupertinoButton(
              key: ValueKey<String>('circle-member-row-${member.id}'),
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              // 成员行进入用户主页：关注/打招呼/私聊由主页既有能力承接，
              // 圈子侧不复制第二套建联入口。
              onPressed: member.id.trim().isEmpty
                  ? null
                  : () => _openMemberProfile(member),
              child: Container(
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
                    SizedBox.square(
                      dimension: AppSpacing.md * 2,
                      child: ClipOval(
                        child: avatarUrl.isEmpty
                            ? ColoredBox(
                                color: AppColorsFunctional.getColor(
                                  widget.isDark,
                                  ColorType.backgroundSecondary,
                                ),
                                child: fallbackAvatar,
                              )
                            : AppAvatarImage(
                                imageUrl: avatarUrl,
                                size: AppSpacing.md * 2,
                                errorWidget: ColoredBox(
                                  color: AppColorsFunctional.getColor(
                                    widget.isDark,
                                    ColorType.backgroundSecondary,
                                  ),
                                  child: fallbackAvatar,
                                ),
                              ),
                      ),
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
                            CommunityText.circleMemberContribution(
                              worksCount: member.worksCountLabel,
                              likesCount: member.likesCountLabel,
                            ),
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
                    Icon(
                      CupertinoIcons.chevron_forward,
                      color: fgSecondary,
                      size: AppSpacing.iconSmall,
                    ),
                  ],
                ),
              ),
            );
          })
          .toList(growable: false),
    );
  }

  /// 成员行 → 用户主页；行内快照（名称/头像）作为主页首屏渐进增强。
  void _openMemberProfile(CircleStatsMemberRowViewData member) {
    final personaId = member.id.trim();
    if (personaId.isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.userProfile(userHandle: personaId),
      extra: UserProfileRouteExtra(
        personaId: personaId,
        avatarUrl: member.avatarUrl.trim().isEmpty ? null : member.avatarUrl,
        displayName: member.name.trim().isEmpty ? null : member.name,
      ),
    );
  }
}
