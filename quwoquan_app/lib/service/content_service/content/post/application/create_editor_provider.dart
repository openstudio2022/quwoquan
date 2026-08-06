import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_editor_projection.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_undo_snapshot.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';

part 'create_editor_provider_document_operations.dart';
part 'create_editor_provider_media_operations.dart';
part 'create_editor_provider_node_editing_operations.dart';
part 'create_editor_provider_node_structure_operations.dart';

class CreateEditorNotifier extends Notifier<CreateEditorState>
    with
        _CreateEditorDocumentOperations,
        _CreateEditorNodeStructureOperations,
        _CreateEditorNodeEditingOperations,
        _CreateEditorMediaOperations {
  @override
  CreateEditorState build() => CreateEditorState.initial();
}

final createEditorProvider =
    NotifierProvider.autoDispose<CreateEditorNotifier, CreateEditorState>(
      CreateEditorNotifier.new,
    );
