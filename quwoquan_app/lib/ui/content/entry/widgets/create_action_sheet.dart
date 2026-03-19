import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

typedef CreateActionSelected = void Function(EditorStartAction action);

class CreateActionSheet extends StatelessWidget {
  const CreateActionSheet({
    super.key,
    required this.onCreateAction,
    required this.onStartGroupChat,
    required this.onAddContact,
    required this.onCancel,
  });

  final CreateActionSelected onCreateAction;
  final VoidCallback onStartGroupChat;
  final VoidCallback onAddContact;
  final VoidCallback onCancel;

  static const String galleryLabel = '从相册选择';
  static const String cameraLabel = '相机';
  static const String writeLabel = '写文字';
  static const String groupChatLabel = '发起群聊';
  static const String addContactLabel = '添加同好';

  @override
  Widget build(BuildContext context) {
    return CupertinoActionSheet(
      actions: <Widget>[
        CupertinoActionSheetAction(
          onPressed: () => onCreateAction(EditorStartAction.gallery),
          child: const Text(galleryLabel, key: TestKeys.createActionGallery),
        ),
        CupertinoActionSheetAction(
          onPressed: () => onCreateAction(EditorStartAction.capture),
          child: const Text(cameraLabel, key: TestKeys.createActionCapture),
        ),
        CupertinoActionSheetAction(
          onPressed: () => onCreateAction(EditorStartAction.write),
          child: const Text(writeLabel, key: TestKeys.createActionWrite),
        ),
        CupertinoActionSheetAction(
          onPressed: onStartGroupChat,
          child: const Text(groupChatLabel),
        ),
        CupertinoActionSheetAction(
          onPressed: onAddContact,
          child: const Text(addContactLabel),
        ),
      ],
      cancelButton: CupertinoActionSheetAction(
        onPressed: onCancel,
        isDefaultAction: true,
        child: const Text('取消'),
      ),
    );
  }
}
