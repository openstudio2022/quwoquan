import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/tag_ref_label.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';
part 'edit_profile_page_sections.dart';
part 'edit_profile_page_phone_qr.dart';

class EditProfilePage extends ConsumerStatefulWidget {
  const EditProfilePage({super.key});

  @override
  ConsumerState<EditProfilePage> createState() => _EditProfilePageState();
}

enum _EditProfileValueTone { regular, prompt }

class _EditProfileDisplayValue {
  const _EditProfileDisplayValue(
    this.text, {
    this.tone = _EditProfileValueTone.regular,
  });

  final String text;
  final _EditProfileValueTone tone;
}

class _EditProfileFormSemantics {
  const _EditProfileFormSemantics._();

  static const double mediaPreviewSize = AppSpacing.buttonHeight;
  static const double mediaRowMinHeight =
      AppSpacing.buttonHeight + AppSpacing.containerSm;
  static const double trailingValueWidth =
      AppSpacing.oneHundred + AppSpacing.buttonHeightMd;

  static TextStyle trailingValueTextStyle(
    BuildContext context,
    _EditProfileValueTone tone,
  ) {
    return TextStyle(
      fontSize: AppTypography.iosSubheadline,
      fontWeight: AppTypography.regular,
      height: AppTypography.lineHeightCompact,
      color: tone == _EditProfileValueTone.prompt
          ? AppColors.iosTertiaryLabel(context)
          : AppColors.iosSecondaryLabel(context),
    );
  }
}

class _EditProfileTrailingValue extends StatelessWidget {
  const _EditProfileTrailingValue({required this.value});

  final _EditProfileDisplayValue value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: _EditProfileFormSemantics.trailingValueWidth,
      child: Text(
        value.text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        textAlign: TextAlign.right,
        style: _EditProfileFormSemantics.trailingValueTextStyle(
          context,
          value.tone,
        ),
      ),
    );
  }
}

class _MediaPreview extends StatelessWidget {
  const _MediaPreview({
    required this.source,
    required this.isAvatar,
    required this.previewKey,
  });

  final String source;
  final bool isAvatar;
  final Key previewKey;

  @override
  Widget build(BuildContext context) {
    final radius = isAvatar
        ? AppSpacing.radiusNinetyNine
        : AppSpacing.radiusTen;
    final child = source.trim().isEmpty
        ? ColoredBox(
            color: AppColors.iosSecondaryFill(context),
            child: Icon(
              isAvatar ? CupertinoIcons.person : CupertinoIcons.photo,
              size: AppSpacing.iconMedium,
              color: AppColors.iosTertiaryLabel(context),
            ),
          )
        : AppMediaImage(
            imageSource: source,
            fit: BoxFit.cover,
            placeholder: const SizedBox.shrink(),
            errorWidget: ColoredBox(
              color: AppColors.iosSecondaryFill(context),
              child: Icon(
                CupertinoIcons.photo,
                size: AppSpacing.iconMedium,
                color: AppColors.iosTertiaryLabel(context),
              ),
            ),
          );
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(
        key: previewKey,
        width: _EditProfileFormSemantics.mediaPreviewSize,
        height: _EditProfileFormSemantics.mediaPreviewSize,
        child: child,
      ),
    );
  }
}

class _TextEditPage extends StatefulWidget {
  const _TextEditPage({
    required this.title,
    required this.initialValue,
    required this.placeholder,
    required this.maxLength,
    required this.maxLines,
  });

  final String title;
  final String initialValue;
  final String placeholder;
  final int maxLength;
  final int maxLines;

  @override
  State<_TextEditPage> createState() => _TextEditPageState();
}

class _TextEditPageState extends State<_TextEditPage> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialValue)
      ..addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final canSave = _controller.text.length <= widget.maxLength;
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
        middle: Text(
          widget.title,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: CupertinoButton(
          key: const ValueKey<String>('edit-profile-text-save'),
          padding: EdgeInsets.zero,
          onPressed: canSave
              ? () => Navigator.of(context).pop(_controller.text.trim())
              : null,
          child: Text(
            UITextConstants.editProfileSaveAction,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
              color: canSave
                  ? AppColors.iosAccent(context)
                  : AppColors.iosTertiaryLabel(context),
            ),
          ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        children: <Widget>[
          CupertinoTextField(
            controller: _controller,
            autofocus: true,
            maxLines: widget.maxLines,
            maxLength: widget.maxLength,
            placeholder: widget.placeholder,
            padding: EdgeInsets.all(AppSpacing.containerMd),
            decoration: BoxDecoration(
              color: AppColors.iosSystemBackground(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            ),
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Text(
              '${widget.maxLength - _controller.text.length}',
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BirthdayEditPage extends StatefulWidget {
  const _BirthdayEditPage({required this.initialValue});

  final String initialValue;

  @override
  State<_BirthdayEditPage> createState() => _BirthdayEditPageState();
}

class _BirthdayEditPageState extends State<_BirthdayEditPage> {
  late DateTime _pickerDate;
  late final TextEditingController _controller;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _pickerDate = _parseBirthday(widget.initialValue) ?? DateTime(2000);
    _controller = TextEditingController(text: widget.initialValue);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
        middle: Text(
          UITextConstants.editProfileBirthdayTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _save,
          child: Text(
            UITextConstants.editProfileSaveAction,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
              color: AppColors.iosAccent(context),
            ),
          ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        children: <Widget>[
          Container(
            height: AppSpacing.twoHundredTwenty,
            decoration: BoxDecoration(
              color: AppColors.iosSystemBackground(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            ),
            child: CupertinoDatePicker(
              mode: CupertinoDatePickerMode.date,
              initialDateTime: _pickerDate,
              minimumDate: DateTime(1900),
              maximumDate: DateTime.now(),
              onDateTimeChanged: (date) {
                _pickerDate = date;
                _controller.text = _formatBirthday(date);
                setState(() => _error = '');
              },
            ),
          ),
          SizedBox(height: AppSpacing.containerMd),
          CupertinoTextField(
            controller: _controller,
            keyboardType: TextInputType.datetime,
            placeholder: UITextConstants.editProfileBirthdayInputPlaceholder,
            padding: EdgeInsets.all(AppSpacing.containerMd),
            decoration: BoxDecoration(
              color: AppColors.iosSystemBackground(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            ),
            onChanged: (_) => setState(() => _error = ''),
          ),
          if (_error.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              _error,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosDestructive(context),
              ),
            ),
          ],
        ],
      ),
    );
  }

  void _save() {
    final parsed = _parseBirthday(_controller.text.trim());
    final today = DateTime.now();
    if (parsed == null ||
        parsed.isBefore(DateTime(1900)) ||
        parsed.isAfter(DateTime(today.year, today.month, today.day))) {
      setState(() => _error = UITextConstants.editProfileBirthdayInvalid);
      return;
    }
    Navigator.of(context).pop(_formatBirthday(parsed));
  }
}

class _RegionPickerPage extends ConsumerStatefulWidget {
  const _RegionPickerPage({required this.selectedTagRef});

  final String selectedTagRef;

  @override
  ConsumerState<_RegionPickerPage> createState() => _RegionPickerPageState();
}

class _RegionPickerPageState extends ConsumerState<_RegionPickerPage> {
  TagChild? _province;
  List<TagChild> _items = const <TagChild>[];
  Object? _error;
  bool _loading = true;
  int _requestSerial = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_loadChildren(TagTaxonomyRefs.chinaAdminRegionRoot));
  }

  Future<void> _loadChildren(String parentTagRef, {TagChild? province}) async {
    final serial = ++_requestSerial;
    setState(() {
      _province = province;
      _loading = true;
      _error = null;
      _items = const <TagChild>[];
    });
    try {
      final items = await ref
          .read(tagRepositoryProvider)
          .listChildren(parentTagRef);
      if (!mounted || serial != _requestSerial) {
        return;
      }
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (error) {
      if (!mounted || serial != _requestSerial) {
        return;
      }
      setState(() {
        _error = error;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (_province != null) {
              unawaited(_loadChildren(TagTaxonomyRefs.chinaAdminRegionRoot));
            } else {
              Navigator.of(context).pop();
            }
          },
        ),
        middle: Text(
          UITextConstants.editProfileRegionTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: _buildBody(context),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return Center(
        child: CupertinoButton(
          onPressed: () => unawaited(
            _loadChildren(
              _province?.tagRef ?? TagTaxonomyRefs.chinaAdminRegionRoot,
              province: _province,
            ),
          ),
          child: const Text(UITextConstants.tryAgain),
        ),
      );
    }
    if (_items.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.profileEmptyRegionOptions,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      );
    }
    return ListView.separated(
      padding: EdgeInsets.only(top: AppSpacing.containerSm),
      itemBuilder: (context, index) {
        if (_province == null) {
          final item = _items[index];
          return _SimplePickRow(
            label: _tagDisplayLabel(item),
            trailingText: _selectedProvinceText(item),
            onTap: () => unawaited(_loadChildren(item.tagRef, province: item)),
          );
        }
        final city = _items[index];
        final isSelected = city.tagRef == widget.selectedTagRef;
        return _SimplePickRow(
          label: _tagDisplayLabel(city),
          trailing: isSelected
              ? Icon(
                  CupertinoIcons.check_mark,
                  size: AppSpacing.iconMedium,
                  color: AppColors.iosAccent(context),
                )
              : null,
          showChevron: false,
          onTap: () {
            Navigator.of(context).pop(
              _RegionPickResult(
                display: _regionDisplayFor(
                  _tagDisplayLabel(_province!),
                  _tagDisplayLabel(city),
                ),
                tagRef: city.tagRef,
              ),
            );
          },
        );
      },
      separatorBuilder: (_, _) => Padding(
        padding: EdgeInsets.only(left: AppSpacing.containerMd),
        child: Container(
          height: AppSpacing.hairline,
          color: AppColors.iosSeparator(context).withValues(alpha: 0.36),
        ),
      ),
      itemCount: _items.length,
    );
  }

  String _selectedProvinceText(TagChild option) {
    final selected = widget.selectedTagRef.startsWith('${option.tagRef}/');
    return selected ? UITextConstants.editProfileSelectedRegion : '';
  }

  String _tagDisplayLabel(TagChild option) {
    final display = option.displayLabel.trim();
    if (display.isNotEmpty) {
      return display;
    }
    return tagRefDisplayLabel(option.tagRef);
  }
}

class _PhoneBindPage extends ConsumerStatefulWidget {
  const _PhoneBindPage({required this.initialCredential});

  final ProfileCredentialSummaryData? initialCredential;

  @override
  ConsumerState<_PhoneBindPage> createState() => _PhoneBindPageState();
}

class _ProfileQrCardPage extends ConsumerWidget {
  const _ProfileQrCardPage();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
        middle: Text(
          UITextConstants.editProfileQrCardTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: FutureBuilder<ProfileQrCardData>(
        future: ref.read(userProfileRepositoryProvider).getProfileQrCard(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CupertinoActivityIndicator());
          }
          return _QrCardBody(card: snapshot.data!);
        },
      ),
    );
  }
}

class _SimplePickRow extends StatelessWidget {
  const _SimplePickRow({
    required this.label,
    this.trailingText = '',
    this.trailing,
    this.showChevron = true,
    required this.onTap,
  });

  final String label;
  final String trailingText;
  final Widget? trailing;
  final bool showChevron;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ProfileIosGroupedCell(
      title: label,
      trailingText: trailingText,
      trailing: trailing,
      showChevron: showChevron,
      onTap: onTap,
    );
  }
}

enum _EditProfileMediaTarget { avatar, cover }

class _RegionPickResult {
  const _RegionPickResult({required this.display, required this.tagRef});

  final String display;
  final String tagRef;
}

String _normalizeGender(String value) {
  return switch (value.trim()) {
    'male' || 'female' => value.trim(),
    _ => 'unspecified',
  };
}

_EditProfileDisplayValue _valueOrPrompt(
  String value, {
  required String prompt,
}) {
  final trimmed = value.trim();
  return trimmed.isEmpty
      ? _EditProfileDisplayValue(prompt, tone: _EditProfileValueTone.prompt)
      : _EditProfileDisplayValue(trimmed);
}

_EditProfileDisplayValue _valueOrSystemFallback(
  String value, {
  required String fallback,
}) {
  final trimmed = value.trim();
  return _EditProfileDisplayValue(trimmed.isEmpty ? fallback : trimmed);
}

String _genderLabel(String value) {
  return switch (_normalizeGender(value)) {
    'male' => UITextConstants.editProfileGenderMale,
    'female' => UITextConstants.editProfileGenderFemale,
    _ => UITextConstants.editProfileGenderUnsetValue,
  };
}

_EditProfileDisplayValue _regionDisplay(String value) {
  if (value.trim().isEmpty) {
    return const _EditProfileDisplayValue(
      UITextConstants.editProfileSelectCtaValue,
      tone: _EditProfileValueTone.prompt,
    );
  }
  final parts = value.trim().split(RegExp(r'\s+'));
  if (parts.length == 2 && parts.first == parts.last) {
    return _EditProfileDisplayValue(parts.first);
  }
  return _EditProfileDisplayValue(value.trim());
}

_EditProfileDisplayValue _phoneDisplay(
  ProfileCredentialSummaryData? credential,
) {
  if (credential == null ||
      !credential.isBound ||
      credential.displayLabel.isEmpty) {
    return const _EditProfileDisplayValue(
      UITextConstants.editProfileBindCtaValue,
      tone: _EditProfileValueTone.prompt,
    );
  }
  return _EditProfileDisplayValue(credential.displayLabel);
}

_EditProfileDisplayValue _tagsSummary(
  String occupation,
  List<String> interests,
) {
  final labels = <String>[
    if (occupation.isNotEmpty) tagRefDisplayLabel(occupation),
    ...interests.map(tagRefDisplayLabel),
  ].where((label) => label.isNotEmpty).toList(growable: false);
  if (labels.isEmpty) {
    return const _EditProfileDisplayValue(
      UITextConstants.editProfileSelectCtaValue,
      tone: _EditProfileValueTone.prompt,
    );
  }
  return _EditProfileDisplayValue(labels.join(' · '));
}

bool _sameStringList(List<String> a, List<String> b) {
  if (a.length != b.length) {
    return false;
  }
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) {
      return false;
    }
  }
  return true;
}

DateTime? _parseBirthday(String value) {
  final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(value.trim());
  if (match == null) {
    return null;
  }
  final year = int.tryParse(match.group(1)!);
  final month = int.tryParse(match.group(2)!);
  final day = int.tryParse(match.group(3)!);
  if (year == null || month == null || day == null) {
    return null;
  }
  final date = DateTime(year, month, day);
  if (date.year != year || date.month != month || date.day != day) {
    return null;
  }
  return date;
}

String _formatBirthday(DateTime date) {
  return '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}

String _regionDisplayFor(String province, String city) {
  return province == city ? province : '$province $city';
}

String _maskPhone(String phone) {
  final trimmed = phone.trim();
  if (trimmed.length <= 7) {
    return trimmed;
  }
  return '${trimmed.substring(0, 3)}****${trimmed.substring(trimmed.length - 4)}';
}

BoxDecoration _inputDecoration(BuildContext context) {
  return BoxDecoration(
    color: AppColors.iosSystemBackground(context),
    borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
  );
}
