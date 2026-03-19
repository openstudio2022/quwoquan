import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';

class CreateEntrySheet extends ConsumerWidget {
  const CreateEntrySheet({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.onSelect,
    this.onOpenLegacyTab,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final void Function(EditorStartAction action) onSelect;
  final void Function(String tabKey)? onOpenLegacyTab;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!isOpen) {
      return const SizedBox.shrink();
    }

    final useSimpleSheet =
        ref.watch(contentFeatureFlagProvider('simple_create_action_sheet')) ||
        ref.watch(contentFeatureFlagProvider('enable_create_action_entry'));

    return Material(
      color: Colors.black54,
      child: SafeArea(
        top: false,
        child: Align(
          alignment: Alignment.bottomCenter,
          child: useSimpleSheet
              ? CreateActionSheet(
                  onCreateAction: onSelect,
                  onStartGroupChat: onClose,
                  onAddContact: onClose,
                  onCancel: onClose,
                )
              : _LegacyFallbackSheet(
                  onClose: onClose,
                  onSelect: onSelect,
                ),
        ),
      ),
    );
  }
}

class _LegacyFallbackSheet extends StatelessWidget {
  const _LegacyFallbackSheet({
    required this.onClose,
    required this.onSelect,
  });

  final VoidCallback onClose;
  final void Function(EditorStartAction action) onSelect;

  @override
  Widget build(BuildContext context) {
    return CreateActionSheet(
      onCreateAction: onSelect,
      onStartGroupChat: onClose,
      onAddContact: onClose,
      onCancel: onClose,
    );
  }
}
