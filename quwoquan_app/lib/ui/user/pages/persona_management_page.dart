// ignore_for_file: unnecessary_underscores

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// 管理分身页（1:1 对应 PersonaManagementPage.tsx）
/// 路由：/profile/personas
class PersonaManagementPage extends ConsumerStatefulWidget {
  const PersonaManagementPage({super.key});

  @override
  ConsumerState<PersonaManagementPage> createState() =>
      _PersonaManagementPageState();
}

class _PersonaManagementPageState extends ConsumerState<PersonaManagementPage> {
  static const int _maxPersonas = 5;
  String _currentId = 'primary';

  /// 1:1 PersonaManagementPage 默认分身列表
  late List<Map<String, dynamic>> _personas;

  @override
  void initState() {
    super.initState();
    _personas = [
      {
        'id': 'primary',
        'displayName': '主账号',
        'name': 'primary',
        'avatar':
            'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
        'isPrimary': true,
        'isPrivate': false,
        'postCount': 42,
        'likeCount': 4200,
      },
      {
        'id': 'p2',
        'displayName': '摄影分身',
        'name': 'photo_persona',
        'avatar':
            'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
        'isPrimary': false,
        'isPrivate': false,
        'postCount': 18,
        'likeCount': 1200,
      },
    ];
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.personaManage,
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.lg,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(
          AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd,
        ),
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.person_outline,
                    size: AppSpacing.twenty,
                    color: AppColors.primaryColor,
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Text(
                    '切换角色',
                    style: TextStyle(
                      fontSize: AppTypography.xl,
                      fontWeight: FontWeight.w900,
                      color: fg,
                    ),
                  ),
                ],
              ),
              Text(
                '已创建 ${_personas.length}/$_maxPersonas',
                style: TextStyle(
                  fontSize: AppTypography.smPlus,
                  fontWeight: FontWeight.w700,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.lg),
          ..._personas.map(
            (p) => _buildPersonaCard(
              persona: p,
              isDark: isDark,
              fg: fg,
              fgSecondary: fgSecondary,
              borderColor: borderColor,
            ),
          ),
          if (_personas.length < _maxPersonas)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: CupertinoButton(
                onPressed: () {},
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.fourteen),
                color: Colors.transparent,
                disabledColor: Colors.transparent,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.fourteen),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(AppSpacing.lg),
                    border: Border.all(color: AppColors.primaryColor),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        CupertinoIcons.add,
                        size: AppSpacing.twenty,
                        color: AppColors.primaryColor,
                      ),
                      SizedBox(width: AppSpacing.sm),
                      Text(
                        '新增分身',
                        style: TextStyle(
                          color: AppColors.primaryColor,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPersonaCard({
    required Map<String, dynamic> persona,
    required bool isDark,
    required Color fg,
    required Color fgSecondary,
    required Color borderColor,
  }) {
    final isActive = _currentId == persona['id'];
    final isPrimary = persona['isPrimary'] as bool? ?? false;
    final likeCount = persona['likeCount'] as int? ?? 0;
    final likeStr = likeCount >= 1000
        ? '${(likeCount / 1000).toStringAsFixed(1)}k'
        : '$likeCount';
    final avatar = persona['avatar'] as String? ?? '';

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: GestureDetector(
        onTap: () => setState(() => _currentId = persona['id'] as String),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.twenty),
          decoration: BoxDecoration(
            color: isActive
                ? AppColors.primaryColor.withValues(alpha: 0.08)
                : AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
            borderRadius: BorderRadius.circular(AppSpacing.lg),
            border: Border.all(
              color: isActive
                  ? AppColors.primaryColor
                  : borderColor.withValues(alpha: 0.5),
              width: isActive ? 2 : 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (isActive)
                Align(
                  alignment: Alignment.topRight,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 4,
                    ),
                    decoration: const BoxDecoration(
                      color: AppColors.primaryColor,
                      borderRadius: BorderRadius.only(
                        bottomLeft: Radius.circular(AppSpacing.md),
                        topRight: Radius.circular(AppTypography.xxxl),
                      ),
                    ),
                    child: const Text(
                      '当前使用',
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        fontWeight: FontWeight.w900,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              if (isActive) const SizedBox(height: AppSpacing.sm),
              Row(
                children: [
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      CircleAvatar(
                        radius: 32,
                        backgroundImage:
                            avatar.isNotEmpty ? NetworkImage(avatar) : null,
                        onBackgroundImageError: (_, __) {},
                        child: avatar.isEmpty
                            ? Icon(Icons.person, color: fgSecondary)
                            : null,
                      ),
                      if (isPrimary)
                        const Positioned(
                          top: -AppSpacing.two,
                          right: -AppSpacing.two,
                          child: Icon(
                            Icons.star,
                            size: AppSpacing.fourteen,
                            color: Colors.amber,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              persona['displayName'] as String? ?? '',
                              style: TextStyle(
                                fontSize: AppTypography.lg,
                                fontWeight: FontWeight.w800,
                                color: fg,
                              ),
                            ),
                            if (persona['isPrivate'] == true) ...[
                              const SizedBox(width: AppSpacing.xs),
                              Icon(
                                Icons.lock,
                                size: AppSpacing.fourteen,
                                color: Colors.purple.shade300,
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          '@${persona['name'] ?? ''}',
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgSecondary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: AppSpacing.sm),
                        Row(
                          children: [
                            _statChip(
                              '作品',
                              '${persona['postCount'] ?? 0}',
                              fgSecondary,
                            ),
                            const SizedBox(width: AppSpacing.md),
                            _statChip('关注', '128', fgSecondary),
                            const SizedBox(width: AppSpacing.md),
                            _statChip('获赞', likeStr, fgSecondary),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.interGroupSm),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  CupertinoButton(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm,
                    ),
                    onPressed: () {}, minimumSize: Size(0, 0),
                    child: const Text(
                      '编辑',
                      style: TextStyle(fontSize: AppTypography.sm),
                    ),
                  ),
                  if (!isPrimary)
                    CupertinoButton(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      onPressed: () {}, minimumSize: Size(0, 0),
                      child: Text(
                        '删除',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundSecondary,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statChip(String label, String value, Color fgSecondary) {
    return Text(
      '$label $value',
      style: TextStyle(
        fontSize: AppTypography.sm,
        fontWeight: FontWeight.w700,
        color: fgSecondary,
      ),
    );
  }
}
