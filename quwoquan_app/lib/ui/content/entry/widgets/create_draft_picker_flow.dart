import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_draft_picker_sheet.dart';

/// 展示与添加菜单同壳的草稿选择底栏，选中后 `go` 到创作页并带上 `draftId` + `type`。
Future<void> presentCreateDraftPickerAndGo(
  BuildContext context,
  GoRouter router,
) async {
  final loaded = await CreateDraftLocalStorage.loadDraftsWithCurrentId();
  if (!context.mounted) {
    return;
  }
  await showCupertinoModalPopup<void>(
    context: context,
    barrierColor: Colors.transparent,
    builder: (sheetContext) {
      return CreateDraftPickerSheet(
        initialDrafts: loaded.drafts,
        onSelect: (CreateDraft draft) {
          Navigator.of(sheetContext).pop();
          router.go(
            Uri(
              path: AppRoutePaths.createPathTemplate,
              queryParameters: <String, String>{
                'draftId': draft.id,
                'type': draft.state.editorKind == CreateEditorKind.text
                    ? EditorStartAction.write.name
                    : EditorStartAction.gallery.name,
              },
            ).toString(),
          );
        },
        onDismiss: () => Navigator.of(sheetContext).pop(),
      );
    },
  );
}
