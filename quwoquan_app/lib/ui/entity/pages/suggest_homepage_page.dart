import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

class SuggestHomepagePage extends ConsumerStatefulWidget {
  const SuggestHomepagePage({super.key, this.initialQuery = ''});

  final String initialQuery;

  @override
  ConsumerState<SuggestHomepagePage> createState() =>
      _SuggestHomepagePageState();
}

class _SuggestHomepagePageState extends ConsumerState<SuggestHomepagePage> {
  late final TextEditingController _titleController;
  final TextEditingController _subtitleController = TextEditingController();
  final TextEditingController _cityController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  String _homepageType = 'sight';
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(text: widget.initialQuery.trim());
  }

  @override
  void dispose() {
    _titleController.dispose();
    _subtitleController.dispose();
    _cityController.dispose();
    _addressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = SettingsSemanticConstants.pageBackground(isDark);
    return CupertinoPageScaffold(
      backgroundColor: background,
      navigationBar: CupertinoNavigationBar(
        middle: const Text('补充主页'),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => context.pop(),
          child: const Icon(CupertinoIcons.xmark),
        ),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: SafeArea(
          top: false,
          child: Column(
            children: <Widget>[
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(
                    AppSpacing.containerMd,
                    AppSpacing.containerSm,
                    AppSpacing.containerMd,
                    AppSpacing.containerLg,
                  ),
                  children: <Widget>[
                    _FormCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          const Text(
                            '补充一个缺失主页',
                            style: TextStyle(
                              fontSize: AppTypography.iosTitle3,
                              fontWeight: AppTypography.semiBold,
                            ),
                          ),
                          SizedBox(height: AppSpacing.intraGroupXs),
                          Text(
                            '提交后会进入审核，审核通过后即可被搜索和关联。',
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              color: CupertinoColors.secondaryLabel.resolveFrom(
                                context,
                              ),
                            ),
                          ),
                          SizedBox(height: AppSpacing.containerMd),
                          _LabeledField(
                            label: '主页名称',
                            child: CupertinoTextField(
                              controller: _titleController,
                              placeholder: '例如 西湖景区 / 竹隐民宿 / Model X',
                            ),
                          ),
                          SizedBox(height: AppSpacing.containerSm),
                          _LabeledField(
                            label: '一句话补充',
                            child: CupertinoTextField(
                              controller: _subtitleController,
                              placeholder: '补充主页的识别信息',
                            ),
                          ),
                          SizedBox(height: AppSpacing.containerSm),
                          _LabeledField(
                            label: '主页类型',
                            child: CupertinoSlidingSegmentedControl<String>(
                              groupValue: _homepageType,
                              children: const <String, Widget>{
                                'sight': Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 8),
                                  child: Text('景点'),
                                ),
                                'hotel': Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 8),
                                  child: Text('酒店'),
                                ),
                                'restaurant': Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 8),
                                  child: Text('餐厅'),
                                ),
                                'vehicle': Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 8),
                                  child: Text('车型'),
                                ),
                              },
                              onValueChanged: (value) {
                                if (value != null) {
                                  setState(() {
                                    _homepageType = value;
                                  });
                                }
                              },
                            ),
                          ),
                          SizedBox(height: AppSpacing.containerSm),
                          _LabeledField(
                            label: '城市',
                            child: CupertinoTextField(
                              controller: _cityController,
                              placeholder: '所在城市',
                            ),
                          ),
                          SizedBox(height: AppSpacing.containerSm),
                          _LabeledField(
                            label: '地址',
                            child: CupertinoTextField(
                              controller: _addressController,
                              placeholder: '更详细的地址或地理描述',
                              maxLines: 3,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  MediaQuery.paddingOf(context).bottom + AppSpacing.containerMd,
                ),
                child: SizedBox(
                  width: double.infinity,
                  height: AppSpacing.buttonHeight,
                  child: CupertinoButton.filled(
                    onPressed: _isSubmitting ? null : _submit,
                    child: _isSubmitting
                        ? const CupertinoActivityIndicator()
                        : const Text('提交补充'),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    if (title.isEmpty) {
      AppToast.show(context, '请先填写主页名称');
      return;
    }
    setState(() {
      _isSubmitting = true;
    });
    try {
      await ref
          .read(homepageRepositoryProvider)
          .suggestHomepageCandidate(
            draft: HomepageSuggestionDraft(
              title: title,
              homepageType: _homepageType,
              subtitle: _subtitleController.text.trim(),
              city: _cityController.text.trim(),
              address: _addressController.text.trim(),
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, '已提交补充，等待审核');
      context.pop(true);
    } catch (_) {
      if (!mounted) {
        return;
      }
      AppToast.show(context, '提交失败，请稍后重试');
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }
}

class _FormCard extends StatelessWidget {
  const _FormCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ),
        ),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: child,
    );
  }
}

class _LabeledField extends StatelessWidget {
  const _LabeledField({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: CupertinoColors.secondaryLabel.resolveFrom(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        child,
      ],
    );
  }
}
