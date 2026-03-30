// ignore_for_file: unnecessary_underscores

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

/// 管理分身页；数据来自 [UserRepository] → [PersonaManagementItemViewData]（清单 PersonaDto 投影）。
/// 路由：/profile/personas
class PersonaManagementPage extends ConsumerStatefulWidget {
  const PersonaManagementPage({super.key});

  @override
  ConsumerState<PersonaManagementPage> createState() =>
      _PersonaManagementPageState();
}

class _PersonaManagementPageState extends ConsumerState<PersonaManagementPage> {
  List<PersonaManagementItemViewData> _personas = const [];
  PersonaManagementQuotaViewData? _quota;
  String _currentId = '';
  bool _loading = true;
  String? _error;

  int get _maxPersonas => _quota?.maxSubAccounts ?? 5;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(_load());
      }
    });
  }

  String _resolveCurrentIdFromSummary(PersonaManagementSummaryViewData s) {
    final ctx = s.activeContext;
    if (ctx != null && ctx.subAccountId.isNotEmpty) return ctx.subAccountId;
    for (final p in s.items) {
      if (p.isActive && p.subAccountId.isNotEmpty) return p.subAccountId;
    }
    for (final p in s.items) {
      if (p.isPrimary) {
        return p.subAccountId.isNotEmpty ? p.subAccountId : p.profileSubjectId;
      }
    }
    if (s.items.isNotEmpty) {
      final p = s.items.first;
      return p.subAccountId.isNotEmpty ? p.subAccountId : p.profileSubjectId;
    }
    return '';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(userRepositoryProvider);
      final summary = await repo.getPersonaManagementSummary();
      if (!mounted) return;
      setState(() {
        _personas = summary.items;
        _quota = summary.quota;
        _currentId = _resolveCurrentIdFromSummary(summary);
        _loading = false;
      });
    } catch (e) {
      try {
        final repo = ref.read(userRepositoryProvider);
        final accounts = await repo.listSubAccounts();
        final activeContext = await repo.getActivePersonaContext();
        if (!mounted) return;
        setState(() {
          _personas = accounts;
          _quota = PersonaManagementQuotaViewData(
            maxSubAccounts: 5,
            usedSubAccounts: accounts.length,
          );
          _currentId = activeContext.subAccountId.isNotEmpty
              ? activeContext.subAccountId
              : (accounts.isNotEmpty
                    ? (accounts.first.subAccountId.isNotEmpty
                          ? accounts.first.subAccountId
                          : accounts.first.profileSubjectId)
                    : '');
          _loading = false;
        });
      } catch (_) {
        if (mounted) {
          setState(() {
            _error = e.toString();
            _loading = false;
          });
        }
      }
    }
  }

  Future<void> _activate(PersonaManagementItemViewData persona) async {
    final id = persona.subAccountId.isNotEmpty
        ? persona.subAccountId
        : persona.profileSubjectId;
    if (id.isEmpty) return;
    try {
      await ref.read(userRepositoryProvider).activateSubAccount(id);
      if (mounted) setState(() => _currentId = id);
      await _load();
    } catch (e) {
      if (mounted) {
        AppToast.show(context, '切换失败：$e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosPageBackground(context);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final accent = AppColors.iosAccent(context);
    final secondaryStyle = isDark
        ? ProfileIosActionStyle.outlined
        : ProfileIosActionStyle.tinted;

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(
          context,
        ).withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.personaManage,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: _loading
          ? const Center(child: CupertinoActivityIndicator())
          : _error != null
          ? Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.containerMd),
                child: Text(
                  _error!,
                  style: TextStyle(color: fgSecondary),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          : ListView(
              padding: EdgeInsets.only(
                top: AppSpacing.containerSm,
                bottom:
                    MediaQuery.viewPaddingOf(context).bottom +
                    AppSpacing.interGroupLg,
              ),
              children: <Widget>[
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                  child: ProfileIosSectionCard(
                    addShadow: true,
                    child: Row(
                      children: <Widget>[
                        Container(
                          width: AppSpacing.buttonSize,
                          height: AppSpacing.buttonSize,
                          decoration: BoxDecoration(
                            color: AppColors.iosTintedFill(context),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            CupertinoIcons.person_2,
                            color: accent,
                            size: AppSpacing.iconMedium,
                          ),
                        ),
                        SizedBox(width: AppSpacing.containerSm),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                '角色切换',
                                style: TextStyle(
                                  fontSize: AppTypography.iosTitle3,
                                  fontWeight: AppTypography.semiBold,
                                  color: fg,
                                  letterSpacing: -0.32,
                                ),
                              ),
                              SizedBox(height: AppSpacing.intraGroupXs),
                              Text(
                                '已创建 ${_personas.length}/$_maxPersonas 个分身，可为不同内容语境切换身份。',
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: fgSecondary,
                                  height: AppSpacing.textLineHeightBody,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                SizedBox(height: AppSpacing.interGroupMd),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                  child: Row(
                    children: <Widget>[
                      Text(
                        '我的分身',
                        style: TextStyle(
                          fontSize: AppTypography.iosSectionHeader,
                          fontWeight: AppTypography.semiBold,
                          color: fgSecondary,
                        ),
                      ),
                      const Spacer(),
                      if (_personas.length < _maxPersonas)
                        ProfileIosActionButton(
                          label: '新增分身',
                          icon: CupertinoIcons.add,
                          onPressed: () =>
                              AppToast.show(context, '新增分身能力待接入'),
                          style: secondaryStyle,
                          expand: false,
                          height: AppSpacing.buttonHeightSm,
                        ),
                    ],
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                ..._personas.map(
                  (p) => _buildPersonaCard(
                    persona: p,
                    fg: fg,
                    fgSecondary: fgSecondary,
                    accent: accent,
                    secondaryStyle: secondaryStyle,
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildPersonaCard({
    required PersonaManagementItemViewData persona,
    required Color fg,
    required Color fgSecondary,
    required Color accent,
    required ProfileIosActionStyle secondaryStyle,
  }) {
    final rowKey = persona.subAccountId.isNotEmpty
        ? persona.subAccountId
        : persona.profileSubjectId;
    final isActive = _currentId == rowKey || (persona.isActive && _currentId.isEmpty);
    final isPrimary = persona.isPrimary;
    final avatar = persona.avatarUrl;
    final isPrivate = persona.profileVisibility != 'public';

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.interGroupSm,
      ),
      child: ProfileIosSectionCard(
        addShadow: isActive,
        backgroundColor: isActive
            ? AppColors.iosTintedFill(context)
            : AppColors.iosGroupedSurface(context),
        borderColor: isActive
            ? accent.withValues(alpha: 0.24)
            : AppColors.iosSeparator(context).withValues(alpha: 0.16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Stack(
                  clipBehavior: Clip.none,
                  children: <Widget>[
                    CircleAvatar(
                      radius: 32,
                      backgroundImage: avatar.isNotEmpty
                          ? NetworkImage(avatar)
                          : null,
                      backgroundColor: AppColors.iosFill(context),
                      onBackgroundImageError: (_, __) {},
                      child: avatar.isEmpty
                          ? Icon(
                              CupertinoIcons.person_crop_circle_fill,
                              color: fgSecondary,
                            )
                          : null,
                    ),
                    if (isPrimary)
                      Positioned(
                        top: -AppSpacing.two,
                        right: -AppSpacing.two,
                        child: Container(
                          width: AppSpacing.twenty,
                          height: AppSpacing.twenty,
                          decoration: BoxDecoration(
                            color: CupertinoColors.systemYellow.resolveFrom(
                              context,
                            ),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            CupertinoIcons.star_fill,
                            size: AppSpacing.ten + AppSpacing.two,
                            color: CupertinoColors.white,
                          ),
                        ),
                      ),
                  ],
                ),
                SizedBox(width: AppSpacing.containerSm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Flexible(
                            child: Text(
                              persona.displayName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.iosTitle3,
                                fontWeight: AppTypography.semiBold,
                                color: fg,
                                letterSpacing: -0.32,
                              ),
                            ),
                          ),
                          if (isPrivate) ...<Widget>[
                            SizedBox(width: AppSpacing.intraGroupXs),
                            Icon(
                              CupertinoIcons.lock_fill,
                              size: AppSpacing.iconSmall,
                              color: AppColors.iosSecondaryLabel(context),
                            ),
                          ],
                        ],
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        '@${persona.profileSubjectId}',
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.containerSm),
                Flexible(
                  fit: FlexFit.loose,
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      decoration: BoxDecoration(
                        color: isActive ? accent : AppColors.iosFill(context),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.radiusTwenty,
                        ),
                      ),
                      child: Text(
                        isActive ? '当前使用' : '未激活',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          fontWeight: AppTypography.semiBold,
                          color: isActive
                              ? CupertinoColors.white
                              : AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            ProfileIosSectionCard(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.containerSm,
              ),
              backgroundColor: AppColors.iosGroupedSurfaceElevated(context),
              borderColor: AppColors.iosSeparator(
                context,
              ).withValues(alpha: 0.12),
              child: Row(
                children: <Widget>[
                  Expanded(child: _statChip('作品', '—', fgSecondary)),
                  Expanded(child: _statChip('关注', '—', fgSecondary)),
                  Expanded(child: _statChip('获赞', '—', fgSecondary)),
                ],
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Row(
              children: <Widget>[
                Expanded(
                  child: ProfileIosActionButton(
                    label: isActive ? '当前身份' : '切换到此身份',
                    icon: isActive
                        ? CupertinoIcons.check_mark
                        : CupertinoIcons.arrow_right_circle,
                    onPressed: isActive ? () {} : () => _activate(persona),
                    style: isActive
                        ? secondaryStyle
                        : ProfileIosActionStyle.filled,
                  ),
                ),
                SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: ProfileIosActionButton(
                    label: '编辑',
                    icon: CupertinoIcons.pencil,
                    onPressed: () => AppToast.show(context, '分身编辑待接入'),
                    style: secondaryStyle,
                  ),
                ),
                if (!isPrimary) ...<Widget>[
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: ProfileIosActionButton(
                      label: '删除',
                      icon: CupertinoIcons.delete,
                      onPressed: () => AppToast.show(context, '分身删除待接入'),
                      style: ProfileIosActionStyle.outlined,
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statChip(String label, String value, Color fgSecondary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs / 2),
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            color: fgSecondary,
          ),
        ),
      ],
    );
  }
}
