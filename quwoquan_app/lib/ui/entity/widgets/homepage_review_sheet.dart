import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/tag_ref_label.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageReviewView;

/// 写评价 sheet 的提交载荷（创建与编辑同构）。
final class HomepageReviewDraftResult {
  const HomepageReviewDraftResult({
    required this.rating,
    required this.body,
    required this.tagRefs,
  });

  final int rating;
  final String body;
  final List<String> tagRefs;
}

/// iOS 风格写评价 sheet：1-5 星 + 正文 + 亮点标签多选。
/// [initial] 非空为编辑/复活预填；[tagOptions] 为主页 tagRefs 候选。
Future<HomepageReviewDraftResult?> showHomepageReviewSheet(
  BuildContext context, {
  HomepageReviewView? initial,
  List<String> tagOptions = const <String>[],
}) {
  return showCupertinoModalPopup<HomepageReviewDraftResult>(
    context: context,
    builder: (context) =>
        _HomepageReviewSheet(initial: initial, tagOptions: tagOptions),
  );
}

final class _HomepageReviewSheet extends StatefulWidget {
  const _HomepageReviewSheet({required this.initial, required this.tagOptions});

  final HomepageReviewView? initial;
  final List<String> tagOptions;

  @override
  State<_HomepageReviewSheet> createState() => _HomepageReviewSheetState();
}

final class _HomepageReviewSheetState extends State<_HomepageReviewSheet> {
  late int _rating = widget.initial?.rating ?? 0;
  late final TextEditingController _bodyController = TextEditingController(
    text: widget.initial?.body ?? '',
  );
  late final Set<String> _selectedTags = <String>{
    ...?widget.initial?.tagRefs,
  };
  String? _validationMessage;

  bool get _isEditing => widget.initial != null;

  List<String> get _tagOptions {
    // 已选标签（含历史评价遗留）始终可见可反选。
    final merged = <String>{...widget.tagOptions, ..._selectedTags};
    return merged.toList(growable: false);
  }

  @override
  void dispose() {
    _bodyController.dispose();
    super.dispose();
  }

  void _submit() {
    if (_rating < 1) {
      setState(
        () => _validationMessage = ObjectHomepageText.homepageReviewRatingRequired,
      );
      return;
    }
    Navigator.of(context).pop(
      HomepageReviewDraftResult(
        rating: _rating,
        body: _bodyController.text.trim(),
        tagRefs: _selectedTags.toList(growable: false),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomModalSurface(
      panelKey: const ValueKey<String>('homepage-review-sheet'),
      onDismiss: () => Navigator.of(context).pop(),
      maxHeightRatio: 0.86,
      child: SafeArea(
        top: false,
        child: ListView(
          shrinkWrap: true,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            0,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
          ),
          children: <Widget>[
            Text(
              _isEditing
                  ? ObjectHomepageText.homepageReviewSheetEditTitle
                  : ObjectHomepageText.homepageReviewSheetTitle,
              style: TextStyle(
                fontSize: AppTypography.iosTitle2,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              ObjectHomepageText.homepageReviewRatingLabel,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Row(
              children: List<Widget>.generate(5, (index) {
                final starValue = index + 1;
                final selected = starValue <= _rating;
                return CupertinoButton(
                  key: ValueKey<String>('homepage-review-star-$starValue'),
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.intraGroupXs,
                  ),
                  minimumSize: Size.zero,
                  onPressed: () => setState(() {
                    _rating = starValue;
                    _validationMessage = null;
                  }),
                  child: Icon(
                    selected
                        ? CupertinoIcons.star_fill
                        : CupertinoIcons.star,
                    size: AppSpacing.iconLarge,
                    color: selected
                        ? AppColors.warning
                        : AppColors.iosTertiaryLabel(context),
                  ),
                );
              }),
            ),
            if (_validationMessage case final message?) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                message,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.error,
                ),
              ),
            ],
            SizedBox(height: AppSpacing.containerSm),
            CupertinoTextField(
              key: const ValueKey<String>('homepage-review-body-field'),
              controller: _bodyController,
              placeholder: ObjectHomepageText.homepageReviewBodyPlaceholder,
              maxLines: 5,
              minLines: 3,
              maxLength: 1000,
              padding: EdgeInsets.all(AppSpacing.containerSm),
              decoration: BoxDecoration(
                color: AppColors.iosSecondaryFill(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              ),
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosLabel(context),
              ),
            ),
            if (_tagOptions.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              Text(
                ObjectHomepageText.homepageReviewTagsLabel,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Wrap(
                spacing: AppSpacing.intraGroupXs,
                runSpacing: AppSpacing.intraGroupXs,
                children: _tagOptions.map((tag) {
                  final selected = _selectedTags.contains(tag);
                  return CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    onPressed: () => setState(() {
                      if (!_selectedTags.remove(tag)) {
                        _selectedTags.add(tag);
                      }
                    }),
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      decoration: BoxDecoration(
                        color: selected
                            ? AppColors.primaryColor.withValues(alpha: 0.14)
                            : AppColors.iosSecondaryFill(context),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.circularBorderRadius,
                        ),
                      ),
                      child: Text(
                        tagRefDisplayLabel(tag),
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: selected
                              ? AppColors.primaryColor
                              : AppColors.iosLabel(context),
                        ),
                      ),
                    ),
                  );
                }).toList(growable: false),
              ),
            ],
            SizedBox(height: AppSpacing.containerMd),
            CupertinoButton.filled(
              key: const ValueKey<String>('homepage-review-submit'),
              onPressed: _submit,
              child: Text(
                _isEditing
                    ? ObjectHomepageText.homepageReviewUpdateAction
                    : ObjectHomepageText.homepageReviewSubmitAction,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
