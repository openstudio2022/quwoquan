import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 私人助理主页
///
/// Tab：记忆/待办/技能；onManageClick→助理管理页
class AssistantHomePage extends ConsumerStatefulWidget {
  const AssistantHomePage({
    super.key,
    required this.onBack,
    required this.onManageClick,
  });

  final VoidCallback onBack;
  final VoidCallback onManageClick;

  @override
  ConsumerState<AssistantHomePage> createState() => _AssistantHomePageState();
}

class _AssistantHomePageState extends ConsumerState<AssistantHomePage> {
  String _activeTab = 'memory'; // memory | tasks | skills

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return Scaffold(
      backgroundColor: bgColor,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(context, fgPrimary, fgSecondary),
            _buildTabBar(isDark, fgPrimary, fgSecondary),
            Expanded(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(24, 0, 24, 40),
                child: _activeTab == 'memory'
                    ? _buildMemoryContent(fgPrimary, fgSecondary)
                    : _activeTab == 'tasks'
                    ? _buildTasksContent(fgPrimary, fgSecondary)
                    : _buildSkillsContent(fgPrimary, fgSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final secondary = AppColorsFunctional.getColor(
      ref.watch(isDarkProvider),
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 24, 16, 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            onPressed: widget.onBack,
            icon: Icon(Icons.arrow_back, size: 24, color: fgPrimary),
          ),
          Text(
            AppConceptConstants.assistantDisplayTitle,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: fgPrimary,
            ),
          ),
          IconButton(
            onPressed: widget.onManageClick,
            icon: Icon(Icons.settings, size: 24, color: secondary),
          ),
        ],
      ),
    );
  }

  Widget _buildTabBar(bool isDark, Color fgPrimary, Color fgSecondary) {
    final tabs = ['记忆', '待办', '技能'];
    final ids = ['memory', 'tasks', 'skills'];
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 24, vertical: 0),
      child: Container(
        padding: EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: isDark
              ? Colors.white.withValues(alpha: 0.08)
              : Colors.black.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: List.generate(3, (i) {
            final active = _activeTab == ids[i];
            return Expanded(
              child: Material(
                color: active
                    ? (isDark
                          ? Colors.white.withValues(alpha: 0.12)
                          : Colors.white)
                    : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                child: InkWell(
                  onTap: () => setState(() => _activeTab = ids[i]),
                  borderRadius: BorderRadius.circular(8),
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Text(
                        tabs[i],
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: active ? fgPrimary : fgSecondary,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }

  Widget _buildMemoryContent(Color fgPrimary, Color fgSecondary) {
    final memoryData = ref
        .watch(appContentRepositoryProvider)
        .assistantMemoryData;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(height: 24),
        TextField(
          decoration: InputDecoration(
            hintText: '搜索你的记忆...',
            hintStyle: TextStyle(color: fgSecondary, fontSize: 14),
            prefixIcon: Icon(Icons.search, size: 20, color: fgSecondary),
            filled: true,
            fillColor: Colors.white.withValues(
              alpha: ref.watch(isDarkProvider) ? 0.08 : 0.06,
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
          ),
        ),
        SizedBox(height: 24),
        Container(
          padding: EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.primaryColor.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: AppColors.primaryColor.withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.auto_awesome,
                    size: 16,
                    color: AppColors.primaryColor,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '今日日报',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ],
              ),
              SizedBox(height: 12),
              Text(
                '今天你发布了1篇关于极简主义的文章，收到了12个赞。在"4:5美学"圈子里与3位同好讨论了光影处理。总体活跃度击败了88%的用户。',
                style: TextStyle(fontSize: 14, color: fgSecondary, height: 1.5),
              ),
            ],
          ),
        ),
        SizedBox(height: 24),
        Text(
          '最近',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: fgSecondary,
          ),
        ),
        SizedBox(height: 16),
        ...memoryData.map((item) {
          return Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () {},
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: ref.watch(isDarkProvider)
                              ? Colors.white.withValues(alpha: 0.1)
                              : Colors.black.withValues(alpha: 0.06),
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            item['icon'] as String? ?? '📷',
                            style: TextStyle(fontSize: 20),
                          ),
                        ),
                      ),
                      SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item['title'] as String? ?? '',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: fgPrimary,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            Text(
                              item['date'] as String? ?? '',
                              style: TextStyle(
                                fontSize: 12,
                                color: fgSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Icon(
                        CupertinoIcons.chevron_forward,
                        color: fgSecondary,
                        size: 20,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildTasksContent(Color fgPrimary, Color fgSecondary) {
    final tasksData = ref
        .watch(appContentRepositoryProvider)
        .assistantTasksData;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(height: 24),
        Row(
          children: [
            Text('日', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('一', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('二', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('三', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('四', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('五', style: TextStyle(fontSize: 10, color: fgSecondary)),
            Text('六', style: TextStyle(fontSize: 10, color: fgSecondary)),
          ],
        ),
        SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '事项',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: fgSecondary,
              ),
            ),
            IconButton(
              onPressed: () {},
              icon: Icon(Icons.add, color: AppColors.primaryColor),
            ),
          ],
        ),
        SizedBox(height: 12),
        ...tasksData.map((task) {
          final completed = task['status'] == 'completed';
          return Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: Container(
              padding: EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: ref.watch(isDarkProvider)
                    ? Colors.white.withValues(alpha: 0.05)
                    : Colors.black.withValues(alpha: 0.03),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.transparent),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    margin: EdgeInsets.only(top: 2),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: completed
                          ? AppColors.primaryColor
                          : Colors.transparent,
                      border: Border.all(
                        color: completed
                            ? AppColors.primaryColor
                            : fgSecondary.withValues(alpha: 0.5),
                        width: 2,
                      ),
                    ),
                    child: completed
                        ? Icon(Icons.check, size: 14, color: Colors.white)
                        : null,
                  ),
                  SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: ref.watch(isDarkProvider)
                                    ? Colors.white.withValues(alpha: 0.1)
                                    : Colors.black.withValues(alpha: 0.06),
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(
                                  color: fgSecondary.withValues(alpha: 0.3),
                                ),
                              ),
                              child: Text(
                                task['category'] as String? ?? '',
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: fgSecondary,
                                ),
                              ),
                            ),
                            Spacer(),
                            Text(
                              task['time'] as String? ?? '',
                              style: TextStyle(
                                fontSize: 11,
                                color: fgSecondary,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: 4),
                        Text(
                          task['title'] as String? ?? '',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: completed ? fgSecondary : fgPrimary,
                            decoration: completed
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildSkillsContent(Color fgPrimary, Color fgSecondary) {
    final skillsValue = ref.watch(assistantSkillMarketProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(height: 24),
        Container(
          padding: EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ref.watch(isDarkProvider)
                ? Colors.white.withValues(alpha: 0.05)
                : Colors.black.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: AppColors.primaryColor.withValues(alpha: 0.25),
            ),
          ),
          child: Row(
            children: [
              Icon(
                Icons.tune,
                size: 18,
                color: AppColors.primaryColor,
              ),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  '默认全订阅已开启，去技能中心做精细管理',
                  style: TextStyle(
                    fontSize: 13,
                    color: fgSecondary,
                  ),
                ),
              ),
              TextButton(
                onPressed: () => context.push(AppRoutePaths.assistantSkills),
                child: const Text('进入'),
              ),
            ],
          ),
        ),
        SizedBox(height: 16),
        ...skillsValue.when(
          data: (skillsData) => skillsData
              .map((skill) {
                final active = skill.enabled;
                return Padding(
                  padding: EdgeInsets.only(bottom: 16),
                  child: Material(
                    color: ref.watch(isDarkProvider)
                        ? Colors.white.withValues(alpha: 0.05)
                        : Colors.black.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(16),
                    child: InkWell(
                      onTap: () async {
                        if (skill.isDefaultFree) {
                          return;
                        }
                        await ref
                            .read(assistantGatewayProvider)
                            .setSkillEnabled(skill.manifest.id, !active);
                        ref.invalidate(assistantSkillMarketProvider);
                      },
                      borderRadius: BorderRadius.circular(16),
                      child: Padding(
                        padding: EdgeInsets.all(20),
                        child: Row(
                          children: [
                            Container(
                              width: 48,
                              height: 48,
                              decoration: BoxDecoration(
                                color: ref.watch(isDarkProvider)
                                    ? Colors.white.withValues(alpha: 0.1)
                                    : Colors.white,
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.06),
                                    blurRadius: 8,
                                    offset: Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Icon(
                                Icons.widgets,
                                color: active
                                    ? AppColors.primaryColor
                                    : fgSecondary,
                                size: 24,
                              ),
                            ),
                            SizedBox(width: 16),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    skill.manifest.name,
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w700,
                                      color: fgPrimary,
                                    ),
                                  ),
                                  SizedBox(height: 4),
                                  Text(
                                    skill.manifest.description,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: fgSecondary,
                                    ),
                                  ),
                                  SizedBox(height: 2),
                                  Text(
                                    '${skill.category} · v${skill.version}',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: fgSecondary.withValues(alpha: 0.8),
                                    ),
                                  ),
                                  Text(
                                    skill.isDefaultFree
                                        ? '默认能力 · 免订阅'
                                        : '${skill.tier.toUpperCase()} 订阅能力',
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: skill.isDefaultFree
                                          ? AppColors.success
                                          : fgSecondary.withValues(alpha: 0.8),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: active
                                    ? AppColors.primaryColor
                                    : fgSecondary.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text(
                                skill.isDefaultFree
                                    ? '默认启用'
                                    : (active ? '已启用' : '点击订阅'),
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: active ? Colors.white : fgSecondary,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              })
              .toList(growable: false),
          loading: () => <Widget>[
            Padding(
              padding: EdgeInsets.only(top: 12),
              child: Center(
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.primaryColor,
                ),
              ),
            ),
          ],
          error: (error, _) => <Widget>[
            Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                '技能加载失败: $error',
                style: TextStyle(color: fgSecondary),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
