import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子作品板块：显示圈内发布的内容 feed
@Deprecated('遗留圈子作品板块，统一改用 SectionCreations。')
class SectionWorks extends StatefulWidget {
  const SectionWorks({
    super.key,
    required this.circleId,
    required this.isDark,
  });

  final String circleId;
  final bool isDark;

  @override
  State<SectionWorks> createState() => _SectionWorksState();
}

class _SectionWorksState extends State<SectionWorks> {
  String _sortMode = 'latest';
  bool _isGridView = true;
  String? _error;

  // Mock posts for now
  List<Map<String, dynamic>> get _posts => List.generate(9, (i) => {
    'id': 'post-${widget.circleId}-$i',
    'title': '作品标题示例 ${i + 1}',
    'image': 'https://images.unsplash.com/photo-${1600000000000 + i * 1111}?q=80&w=400',
    'likes': 24 + i * 5,
    'date': '2024.02.${(i + 1).toString().padLeft(2, '0')}',
  });

  void _retry() {
    setState(() {
      _error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return _buildErrorCard();
    }
    final fgPrimary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);

    return Column(
      children: [
        _buildToolbar(fgPrimary, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        if (_isGridView)
          _buildGridView(fgSecondary)
        else
          _buildListView(fgPrimary, fgSecondary),
      ],
    );
  }

  Widget _buildToolbar(Color fgPrimary, Color fgSecondary) {
    final sorts = [
      ('latest', UITextConstants.circleSubAll),
      ('hot', '最热'),
      ('featured', '精选'),
    ];
    return Row(
      children: [
        Expanded(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: sorts.map((s) {
                final selected = _sortMode == s.$1;
                return Padding(
                  padding: EdgeInsets.only(right: AppSpacing.sm),
                  child: GestureDetector(
                    onTap: () => setState(() => _sortMode = s.$1),
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.md,
                        vertical: AppSpacing.sm,
                      ),
                      decoration: BoxDecoration(
                        color: selected
                            ? (widget.isDark ? Colors.white.withValues(alpha: 0.1) : Colors.black.withValues(alpha: 0.06))
                            : null,
                        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                        border: Border.all(
                          color: widget.isDark ? Colors.white24 : Colors.black12,
                        ),
                      ),
                      child: Text(
                        s.$2,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.extraBold,
                          color: selected ? fgPrimary : fgSecondary,
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
        IconButton(
          icon: Icon(
            _isGridView ? Icons.view_list : Icons.grid_view,
            color: fgSecondary,
          ),
          onPressed: () => setState(() => _isGridView = !_isGridView),
        ),
      ],
    );
  }

  Widget _buildGridView(Color fgSecondary) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisSpacing: AppSpacing.sm,
        crossAxisSpacing: AppSpacing.sm,
        childAspectRatio: 1,
      ),
      itemCount: _posts.length,
      itemBuilder: (_, i) => ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Image.network(
          _posts[i]['image'] as String,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => Container(
            color: fgSecondary.withValues(alpha: 0.2),
          ),
        ),
      ),
    );
  }

  Widget _buildListView(Color fgPrimary, Color fgSecondary) {
    return Column(
      children: _posts.map((post) => Padding(
        padding: EdgeInsets.only(bottom: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: widget.isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(AppSpacing.xl),
            border: Border.all(color: widget.isDark ? Colors.white12 : Colors.black12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.md),
                child: Image.network(
                  post['image'] as String,
                  height: 120,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) => Container(
                    height: 120,
                    color: fgSecondary.withValues(alpha: 0.2),
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                post['title'] as String,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.extraBold,
                  color: fgPrimary,
                ),
              ),
              Text(
                '${post['date']} · ${post['likes']} 获赞',
                style: TextStyle(
                  fontSize: AppTypography.xsPlus,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      )).toList(),
    );
  }

  Widget _buildErrorCard() {
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    return Container(
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Column(
        children: [
          Icon(Icons.error_outline, color: fgSecondary, size: AppSpacing.iconLarge),
          SizedBox(height: AppSpacing.sm),
          Text('加载失败', style: TextStyle(color: fgSecondary, fontSize: AppTypography.base)),
          SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            onPressed: _retry,
            child: Text('重试', style: TextStyle(color: AppColors.primaryColor, fontSize: AppTypography.base)),
          ),
        ],
      ),
    );
  }
}
