import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

typedef CreateActionSelected = void Function(EditorStartAction action);

enum CreateActionSheetPriority { createPrimary, socialPrimary }

class CreateActionSheet extends StatelessWidget {
  const CreateActionSheet({
    super.key,
    required this.onCreateAction,
    required this.onStartGroupChat,
    required this.onAddContact,
    required this.onCancel,
    this.priority = CreateActionSheetPriority.createPrimary,
  });

  final CreateActionSelected onCreateAction;
  final VoidCallback onStartGroupChat;
  final VoidCallback onAddContact;
  final VoidCallback onCancel;
  final CreateActionSheetPriority priority;

  static const String galleryLabel = '从相册选择';
  static const String cameraLabel = '相机';
  static const String writeLabel = '写文字';
  static const String groupChatLabel = '发起群聊';
  static const String addContactLabel = '添加同好';

  @override
  Widget build(BuildContext context) {
    final sections = priority == CreateActionSheetPriority.createPrimary
        ? <_ActionSection>[
            _ActionSection(
              title: '创作',
              isPrimary: true,
              items: <_ActionItem>[
                _ActionItem(
                  label: galleryLabel,
                  textKey: TestKeys.createActionGallery,
                  onPressed: () => onCreateAction(EditorStartAction.gallery),
                ),
                _ActionItem(
                  label: cameraLabel,
                  textKey: TestKeys.createActionCapture,
                  onPressed: () => onCreateAction(EditorStartAction.capture),
                ),
                _ActionItem(
                  label: writeLabel,
                  textKey: TestKeys.createActionWrite,
                  onPressed: () => onCreateAction(EditorStartAction.write),
                ),
              ],
            ),
            _ActionSection(
              title: '连接',
              items: <_ActionItem>[
                _ActionItem(label: groupChatLabel, onPressed: onStartGroupChat),
                _ActionItem(label: addContactLabel, onPressed: onAddContact),
              ],
            ),
          ]
        : <_ActionSection>[
            _ActionSection(
              title: '连接',
              isPrimary: true,
              items: <_ActionItem>[
                _ActionItem(label: groupChatLabel, onPressed: onStartGroupChat),
                _ActionItem(label: addContactLabel, onPressed: onAddContact),
              ],
            ),
            _ActionSection(
              title: '创作',
              items: <_ActionItem>[
                _ActionItem(
                  label: galleryLabel,
                  textKey: TestKeys.createActionGallery,
                  onPressed: () => onCreateAction(EditorStartAction.gallery),
                ),
                _ActionItem(
                  label: cameraLabel,
                  textKey: TestKeys.createActionCapture,
                  onPressed: () => onCreateAction(EditorStartAction.capture),
                ),
                _ActionItem(
                  label: writeLabel,
                  textKey: TestKeys.createActionWrite,
                  onPressed: () => onCreateAction(EditorStartAction.write),
                ),
              ],
            ),
          ];
    final borderColor = CupertinoColors.separator
        .resolveFrom(context)
        .withValues(alpha: 0.16);
    final backgroundColor = CupertinoColors.systemBackground
        .resolveFrom(context)
        .withValues(alpha: 0.9);

    return Align(
      alignment: Alignment.bottomCenter,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.intraGroupXs,
            0,
            AppSpacing.intraGroupXs,
            AppSpacing.intraGroupXs,
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(
              AppSpacing.twenty + AppSpacing.xs,
            ),
            child: BackdropFilter(
              filter: ImageFilter.blur(
                sigmaX: AppSpacing.containerSm,
                sigmaY: AppSpacing.containerSm,
              ),
              child: Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  color: backgroundColor,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.twenty + AppSpacing.xs,
                  ),
                  border: Border.all(
                    color: borderColor,
                    width: AppSpacing.hairline,
                  ),
                  boxShadow: <BoxShadow>[
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.08),
                      blurRadius: AppSpacing.twenty,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Padding(
                      padding: EdgeInsets.only(
                        top: AppSpacing.sm,
                        bottom: AppSpacing.intraGroupSm,
                      ),
                      child: Center(
                        child: Container(
                          width: AppSpacing.forty,
                          height: AppSpacing.xs,
                          decoration: BoxDecoration(
                            color: CupertinoColors.systemGrey3.resolveFrom(
                              context,
                            ),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.xs / 2,
                            ),
                          ),
                        ),
                      ),
                    ),
                    for (
                      int index = 0;
                      index < sections.length;
                      index++
                    ) ...<Widget>[
                      if (index > 0)
                        Divider(height: AppSpacing.one, color: borderColor),
                      _buildSection(context, sections[index], borderColor),
                    ],
                    Divider(height: AppSpacing.one, color: borderColor),
                    _buildCancelAction(context),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSection(
    BuildContext context,
    _ActionSection section,
    Color borderColor,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.containerSm,
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
          ),
          child: Text(
            section.title,
            style: TextStyle(
              color: section.isPrimary
                  ? AppColors.iosAccentLight.withValues(alpha: 0.88)
                  : CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
              letterSpacing: 0.4,
            ),
          ),
        ),
        for (int index = 0; index < section.items.length; index++) ...<Widget>[
          _buildActionRow(
            context,
            section.items[index],
            emphasize: section.isPrimary,
          ),
          if (index != section.items.length - 1)
            Divider(
              indent: AppSpacing.containerMd,
              endIndent: AppSpacing.containerMd,
              height: AppSpacing.one,
              color: borderColor,
            ),
        ],
      ],
    );
  }

  Widget _buildActionRow(
    BuildContext context,
    _ActionItem item, {
    required bool emphasize,
  }) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: item.onPressed,
      child: SizedBox(
        height: AppSpacing.buttonHeight + AppSpacing.intraGroupXs,
        child: Center(
          child: Text(
            item.label,
            key: item.textKey,
            style: TextStyle(
              color: AppColors.iosAccentLight,
              fontSize: AppTypography.lg,
              fontWeight: emphasize
                  ? AppTypography.semiBold
                  : AppTypography.medium,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCancelAction(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onCancel,
      child: SizedBox(
        height: AppSpacing.buttonHeight + AppSpacing.containerSm,
        child: Center(
          child: Text(
            '取消',
            style: TextStyle(
              color: CupertinoColors.label
                  .resolveFrom(context)
                  .withValues(alpha: 0.88),
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ),
      ),
    );
  }
}

class _ActionSection {
  const _ActionSection({
    required this.title,
    required this.items,
    this.isPrimary = false,
  });

  final String title;
  final List<_ActionItem> items;
  final bool isPrimary;
}

class _ActionItem {
  const _ActionItem({
    required this.label,
    required this.onPressed,
    this.textKey,
  });

  final String label;
  final VoidCallback onPressed;
  final Key? textKey;
}
