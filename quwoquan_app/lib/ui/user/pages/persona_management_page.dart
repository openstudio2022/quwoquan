// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        foregroundColor: fg,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: Text(
          UITextConstants.personaManage,
          style: TextStyle(
            color: fg,
            fontSize: 18,
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
                  Icon(Icons.person_outline, size: 20, color: AppColors.primaryColor),
                  SizedBox(width: 8),
                  Text(
                    '切换角色',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w900,
                      color: fg,
                    ),
                  ),
                ],
              ),
              Text(
                '已创建 ${_personas.length}/$_maxPersonas',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
          SizedBox(height: 24),
          ..._personas.map((p) {
            final isActive = _currentId == p['id'];
            final isPrimary = p['isPrimary'] as bool? ?? false;
            final likeCount = p['likeCount'] as int? ?? 0;
            final likeStr =
                likeCount >= 1000 ? '${(likeCount / 1000).toStringAsFixed(1)}k' : '$likeCount';
            return Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Material(
                color: isActive
                    ? AppColors.primaryColor.withValues(alpha: 0.08)
                    : AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                borderRadius: BorderRadius.circular(24),
                child: InkWell(
                  onTap: () => setState(() => _currentId = p['id'] as String),
                  borderRadius: BorderRadius.circular(24),
                  child: Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(24),
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
                              decoration: BoxDecoration(
                                color: AppColors.primaryColor,
                                borderRadius: BorderRadius.only(
                                  bottomLeft: Radius.circular(16),
                                ),
                              ),
                              child: Text(
                                '当前使用',
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w900,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                        if (isActive) SizedBox(height: 8),
                        Row(
                          children: [
                            Stack(
                              clipBehavior: Clip.none,
                              children: [
                                CircleAvatar(
                                  radius: 32,
                                  backgroundImage: (p['avatar'] as String?) != null &&
                                          (p['avatar'] as String).isNotEmpty
                                      ? NetworkImage(p['avatar'] as String)
                                      : null,
                                  onBackgroundImageError: (_, __) {},
                                  child: (p['avatar'] as String?) == null ||
                                          (p['avatar'] as String).isEmpty
                                      ? Icon(Icons.person, color: fgSecondary)
                                      : null,
                                ),
                                if (isPrimary)
                                  Positioned(
                                    top: -2,
                                    right: -2,
                                    child: Icon(
                                      Icons.star,
                                      size: 14,
                                      color: Colors.amber,
                                    ),
                                  ),
                              ],
                            ),
                            SizedBox(width: 16),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        p['displayName'] as String? ?? '',
                                        style: TextStyle(
                                          fontSize: 16,
                                          fontWeight: FontWeight.w800,
                                          color: fg,
                                        ),
                                      ),
                                      if (p['isPrivate'] == true) ...[
                                        SizedBox(width: 4),
                                        Icon(
                                          Icons.lock,
                                          size: 14,
                                          color: Colors.purple.shade300,
                                        ),
                                      ],
                                    ],
                                  ),
                                  SizedBox(height: 4),
                                  Text(
                                    '@${p['name'] ?? ''}',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: fgSecondary,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  SizedBox(height: 8),
                                  Row(
                                    children: [
                                      _statChip('作品', '${p['postCount'] ?? 0}', fgSecondary),
                                      SizedBox(width: 16),
                                      _statChip('关注', '128', fgSecondary),
                                      SizedBox(width: 16),
                                      _statChip('获赞', likeStr, fgSecondary),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            TextButton(
                              onPressed: () {},
                              child: Text('编辑', style: TextStyle(fontSize: 12)),
                            ),
                            if (!isPrimary)
                              TextButton(
                                onPressed: () {},
                                child: Text(
                                  '删除',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: AppColorsFunctional.getColor(
                                        isDark, ColorType.foregroundSecondary),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }),
          if (_personas.length < _maxPersonas)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: OutlinedButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.add, size: 20),
                label: const Text('新增分身'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(24),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _statChip(String label, String value, Color fgSecondary) {
    return Text(
      '$label $value',
      style: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w700,
        color: fgSecondary,
      ),
    );
  }
}
