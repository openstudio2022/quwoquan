import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 聊天设置/聊天信息页（1:1 图二）
class ChatSettingsPage extends ConsumerStatefulWidget {
  const ChatSettingsPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ChatSettingsPage> createState() => _ChatSettingsPageState();
}

class _ChatSettingsPageState extends ConsumerState<ChatSettingsPage> {
  bool _mute = false;
  bool _pin = false;
  bool _privacyShield = false;
  bool _membersExpanded = false;

  static const int _memberColumns = 5;

  /// 收起时最多 4 行，添加按钮与成员同一行（不单独成行、无空行）
  static const int _memberSlotsCollapsed =
      (_memberColumns * 4) - 1; // 19 成员 + 1 添加 = 20 格 = 4 行
  /// 展开时最多 5 行
  static const int _memberSlotsExpanded =
      (_memberColumns * 5) - 1; // 24 成员 + 1 添加 = 25 格 = 5 行

  static const List<Map<String, String>> _mockMembers = [
    {
      'name': '成员一',
      'username': 'member1',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '成员二',
      'username': 'member2',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '成员三',
      'username': 'member3',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
    },
    {
      'name': '成员四',
      'username': 'member4',
      'avatar':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200',
    },
    {
      'name': '成员五',
      'username': 'member5',
      'avatar':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
    },
    {
      'name': '成员六',
      'username': 'member6',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
    },
    {
      'name': '成员七',
      'username': 'member7',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '成员八',
      'username': 'member8',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '成员九',
      'username': 'member9',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
    },
    {
      'name': '成员十',
      'username': 'member10',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '成员十一',
      'username': 'member11',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '成员十二',
      'username': 'member12',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
    },
    {
      'name': '成员十三',
      'username': 'member13',
      'avatar':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200',
    },
    {
      'name': '成员十四',
      'username': 'member14',
      'avatar':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
    },
    {
      'name': '成员十五',
      'username': 'member15',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
    },
    {
      'name': '成员十六',
      'username': 'member16',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '成员十七',
      'username': 'member17',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '成员十八',
      'username': 'member18',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
    },
    {
      'name': '成员十九',
      'username': 'member19',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
    },
    {
      'name': '成员二十',
      'username': 'member20',
      'avatar':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200',
    },
    {
      'name': '成员廿一',
      'username': 'member21',
      'avatar':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
    },
  ];

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockSurface = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final memberCount = _mockMembers.length;

    final dividerColor = SettingsSemanticConstants.dividerColor(isDark);
    return Scaffold(
      backgroundColor: pageBg,
      appBar: AppBar(
        backgroundColor: blockSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: Text(
          '${UITextConstants.chatInfoTitle}($memberCount)',
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
        actions: [
          if (memberCount > 5)
            IconButton(
              icon: const Icon(Icons.search),
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('${UITextConstants.search}（开发中）')),
                );
              },
            ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Container(height: AppSpacing.one, color: dividerColor),
        ),
      ),
      body: SizedBox.expand(
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(
            left: 0,
            right: 0,
            top: 0,
            bottom: AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
          ),
          children: [
            _section(
              context,
              blockSurface: blockSurface,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final maxMembers = _membersExpanded
                          ? _memberSlotsExpanded
                          : _memberSlotsCollapsed;
                      final visibleCount = _mockMembers.length > maxMembers
                          ? maxMembers
                          : _mockMembers.length;
                      final totalCells = visibleCount + 1;
                      return GridView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: _memberColumns,
                          childAspectRatio: 0.85,
                          crossAxisSpacing: AppSpacing.sm,
                          mainAxisSpacing: AppSpacing.sm,
                        ),
                        itemCount: totalCells,
                        itemBuilder: (context, index) {
                          if (index == visibleCount) {
                            return Align(
                              alignment: Alignment.topCenter,
                              child: _AddMemberPlaceholder(
                                borderColor: borderColor,
                                avatarHeight: AppSpacing.largeButtonSize,
                                onTap: () => context.push(
                                  '/chat/${widget.conversationId}/add-members',
                                ),
                              ),
                            );
                          }
                          final m = _mockMembers[index];
                          final username = m['username'] ?? 'user_$index';
                          return _MemberAvatar(
                            name: m['name']!,
                            avatarUrl: m['avatar'] ?? '',
                            textColor: fgPrimary,
                            username: username,
                            onTap: () => context.push('/user/$username'),
                          );
                        },
                      );
                    },
                  ),
                  if (_mockMembers.length > _memberSlotsCollapsed) ...[
                    SizedBox(height: AppSpacing.xs),
                    Center(
                      child: GestureDetector(
                        onTap: () => setState(
                          () => _membersExpanded = !_membersExpanded,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _membersExpanded
                                  ? UITextConstants.collapseMembers
                                  : UITextConstants.moreMembers,
                              style: TextStyle(
                                fontSize: AppTypography.md,
                                color: fgPrimary.withValues(alpha: 0.75),
                              ),
                            ),
                            SizedBox(width: AppSpacing.xs),
                            Icon(
                              _membersExpanded
                                  ? Icons.keyboard_arrow_up
                                  : Icons.keyboard_arrow_down,
                              size: AppSpacing.iconMedium,
                              color: fgPrimary.withValues(alpha: 0.75),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              context,
              blockSurface: blockSurface,
              child: Column(
                children: [
                  _SettingsRow(
                    label: UITextConstants.groupName,
                    fgPrimary: fgPrimary,
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '示例群聊',
                          style: TextStyle(
                            fontSize: AppTypography.md,
                            color: fgPrimary,
                          ),
                        ),
                        Icon(
                          CupertinoIcons.chevron_forward,
                          size: AppSpacing.iconMedium,
                          color: secondaryColor,
                        ),
                      ],
                    ),
                    onTap: () {},
                  ),
                  _divider(isDark),
                  _SettingsRow(
                    label: UITextConstants.qrCode,
                    fgPrimary: fgPrimary,
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.qr_code_2,
                          size: AppSpacing.iconMedium,
                          color: fgPrimary,
                        ),
                        Icon(
                          CupertinoIcons.chevron_forward,
                          size: AppSpacing.iconMedium,
                          color: secondaryColor,
                        ),
                      ],
                    ),
                    onTap: () {},
                  ),
                  _divider(isDark),
                  _SettingsRow(
                    label: UITextConstants.groupAnnouncement,
                    fgPrimary: fgPrimary,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: secondaryColor,
                    ),
                    onTap: () {},
                  ),
                ],
              ),
            ),
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              context,
              blockSurface: blockSurface,
              child: Column(
                children: [
                  _SettingsRow(
                    label: UITextConstants.muteNotifications,
                    trailing: _buildSettingSwitch(
                      isDark: isDark,
                      value: _mute,
                      onChanged: (v) => setState(() => _mute = v),
                    ),
                  ),
                  _divider(isDark),
                  _SettingsRow(
                    label: UITextConstants.pinChat,
                    trailing: _buildSettingSwitch(
                      isDark: isDark,
                      value: _pin,
                      onChanged: (v) => setState(() => _pin = v),
                    ),
                  ),
                  _divider(isDark),
                  _SettingsRow(
                    label: UITextConstants.privacyShield,
                    trailing: _buildSettingSwitch(
                      isDark: isDark,
                      value: _privacyShield,
                      onChanged: (v) => setState(() => _privacyShield = v),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              context,
              blockSurface: blockSurface,
              child: Column(
                children: [
                  _SettingsRow(
                    label: UITextConstants.setChatBackground,
                    fgPrimary: fgPrimary,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: secondaryColor,
                    ),
                    onTap: () {},
                  ),
                  _divider(isDark),
                  _SettingsRow(
                    label: UITextConstants.clearChatHistory,
                    fgPrimary: fgPrimary,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: secondaryColor,
                    ),
                    onTap: () {},
                  ),
                ],
              ),
            ),
            SizedBox(height: SettingsSemanticConstants.blockSpacing),
            _section(
              context,
              blockSurface: blockSurface,
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('${UITextConstants.exitGroupChat}（开发中）'),
                      ),
                    );
                  },
                  child: SizedBox(
                    width: double.infinity,
                    height: AppSpacing.buttonHeight,
                    child: Center(
                      child: Text(
                        UITextConstants.exitGroupChat,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w500,
                          color: SettingsSemanticConstants.exitActionColor(
                            isDark,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section(
    BuildContext context, {
    required Color blockSurface,
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.only(
        left: SettingsSemanticConstants.blockHorizontalPadding,
        right: SettingsSemanticConstants.blockHorizontalPadding,
        top: SettingsSemanticConstants.sectionVerticalPadding,
        bottom: SettingsSemanticConstants.sectionVerticalPadding,
      ),
      decoration: BoxDecoration(
        color: blockSurface,
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.blockBorderRadius,
        ),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(
            ref.watch(isDarkProvider),
          ),
        ),
      ),
      child: child,
    );
  }

  /// 功能块内分割线：语义 token，非常细、浅
  Widget _divider(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.xs / 2),
      child: Divider(
        height: AppSpacing.one,
        thickness: SettingsSemanticConstants.dividerThickness,
        color: SettingsSemanticConstants.dividerColor(isDark),
      ),
    );
  }

  /// 设置项开关：语义 token。选中时轨道蓝、拇指白；未选中时轨道浅灰、拇指纯白（避免与背景融在一起）
  Widget _buildSettingSwitch({
    required bool isDark,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Transform.scale(
      scale: 0.82,
      alignment: Alignment.centerRight,
      child: Switch(
        value: value,
        onChanged: onChanged,
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        trackOutlineWidth: WidgetStateProperty.all(
          SettingsSemanticConstants.switchTrackOutlineWidth,
        ),
        activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
        activeThumbColor: SettingsSemanticConstants.switchActiveThumbColor,
        inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(
          isDark,
        ),
        thumbColor: WidgetStateProperty.all(Colors.white),
      ),
    );
  }
}

class _MemberAvatar extends StatelessWidget {
  const _MemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.textColor,
    required this.username,
    required this.onTap,
  });

  final String name;
  final String avatarUrl;
  final Color textColor;
  final String username;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircleAvatar(
            radius: AppSpacing.avatarUserXs,
            backgroundImage: NetworkImage(avatarUrl),
          ),
          SizedBox(height: AppSpacing.xs),
          SizedBox(
            width: AppSpacing.largeButtonSize,
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: AppTypography.xs, color: textColor),
            ),
          ),
        ],
      ),
    );
  }
}

class _AddMemberPlaceholder extends StatelessWidget {
  const _AddMemberPlaceholder({
    required this.borderColor,
    required this.avatarHeight,
    required this.onTap,
  });

  final Color borderColor;
  final double avatarHeight;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: avatarHeight * 1.2,
        height: avatarHeight,
        decoration: BoxDecoration(
          border: Border.all(color: borderColor, style: BorderStyle.solid),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        ),
        child: Icon(Icons.add, size: AppSpacing.iconMedium, color: borderColor),
      ),
    );
  }
}

class _SettingsRow extends StatelessWidget {
  const _SettingsRow({
    required this.label,
    required this.trailing,
    this.fgPrimary,
    this.onTap,
  });

  final String label;
  final Widget trailing;
  final Color? fgPrimary;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final color = fgPrimary ?? Theme.of(context).colorScheme.onSurface;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: AppSpacing.buttonHeight),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(fontSize: AppTypography.lg, color: color),
                ),
              ),
              trailing,
            ],
          ),
        ),
      ),
    );
  }
}
