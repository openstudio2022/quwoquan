import 'package:flutter/material.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';

class CreateEntrySheet extends StatelessWidget {
  const CreateEntrySheet({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.onSelect,
    required this.onContinueFromDraft,
    this.priority = CreateActionSheetPriority.createPrimary,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final void Function(EditorStartAction action) onSelect;
  final VoidCallback onContinueFromDraft;
  final CreateActionSheetPriority priority;

  @override
  Widget build(BuildContext context) {
    if (!isOpen) {
      return const SizedBox.shrink();
    }

    return CreateActionSheet(
      onCreateAction: onSelect,
      onContinueFromDraft: onContinueFromDraft,
      onStartGroupChat: onClose,
      onAddContact: onClose,
      onCancel: onClose,
      priority: priority,
    );
  }
}
