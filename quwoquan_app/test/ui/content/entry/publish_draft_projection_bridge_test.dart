import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

void main() {
  group('publish_draft_projection_bridge', () {
    test(
      'createEditorStateToArticlePreviewWire carries Markdown + template keys',
      () {
        final state = CreateEditorState.initial();
        final wire = createEditorStateToArticlePreviewWire(
          state,
          previewPostId: 'p_preview',
        );
        expect(wire['postId'], 'p_preview');
        expect(wire['contentType'], 'article');
        expect(wire['articleMarkdown'], isA<String>());
        expect(wire['articleAssetManifest'], isA<Map>());
        expect(wire['articleRenderProfile'], isA<Map>());
        expect(wire.containsKey('articleDocument'), isFalse);
        expect(wire['articleTemplate'], isNotNull);
        expect(wire['articleFontPreset'], isNotNull);
      },
    );

    test(
      'projectArticleDetailViewFromCreateEditorState returns view for initial draft',
      () {
        final state = CreateEditorState.initial();
        final view = projectArticleDetailViewFromCreateEditorState(state);
        expect(view.id, 'draft_preview');
        expect(view.pages, isNotEmpty);
      },
    );

    test(
      'postReadPreviewBundleFromCreateEditorState uses draftPreview surface',
      () {
        final state = CreateEditorState.initial().copyWith(title: 'NavTitle');
        final bundle = postReadPreviewBundleFromCreateEditorState(state);
        expect(bundle.surface, PostReadSurfaceId.draftPreview);
        expect(bundle.presentation.postId, 'draft_preview');
        expect(bundle.presentation.title, 'NavTitle');
      },
    );

    test(
      'postReadPreviewBundleFromPublishConfirmSummary work article branch',
      () {
        final bundle = postReadPreviewBundleFromPublishConfirmSummary(
          contentIdentity: CreateContentIdentity.work,
          title: 'T',
          body: 'B',
          hasVideo: false,
          imageCount: 0,
        );
        expect(bundle.surface, PostReadSurfaceId.draftPreview);
        expect(bundle.presentation.title, 'T');
        expect(bundle.presentation.body, 'B');
      },
    );

    test('createPublishConfirmPreviewWire video uses contentType video', () {
      final wire = createPublishConfirmPreviewWire(
        contentIdentity: CreateContentIdentity.moment,
        title: '',
        body: 'caption',
        hasVideo: true,
        imageCount: 0,
      );
      expect(wire['contentType'], 'video');
      expect(wire['contentIdentity'], 'moment');
    });

    test(
      'buildCreatePostPayloadMap article branch uses Markdown truth source',
      () {
        final state = CreateEditorState.initial().copyWith(
          title: 'T',
          body: 'x' * 200,
        );
        expect(shouldPublishAsArticleForPayload(state), isTrue);
        final payload = buildCreatePostPayloadMap(state);
        expect(payload['contentType'], 'article');
        expect(payload['articleMarkdown'], isA<String>());
        expect(payload['articleMarkdownVersion'], 'qwq-rich-md/1');
        expect(payload['articleAssetManifest'], isA<Map>());
        expect(payload['articleRenderProfile'], isA<Map>());
        expect(payload.containsKey('articleDocument'), isFalse);
      },
    );
  });
}
