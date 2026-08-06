import 'package:flutter/material.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_action_sheet.dart';

class CreateEntrySheet extends StatelessWidget {
  const CreateEntrySheet({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.onSelect,
    required this.onStartGathering,
    required this.onStartGroupChat,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final void Function(EditorStartAction action) onSelect;
  final VoidCallback onStartGathering;
  final VoidCallback onStartGroupChat;

  @override
  Widget build(BuildContext context) {
    if (!isOpen) {
      return const SizedBox.shrink();
    }

    return CreateActionSheet(
      onCreateAction: onSelect,
      onStartGathering: onStartGathering,
      onStartGroupChat: onStartGroupChat,
      onCancel: onClose,
    );
  }
}
