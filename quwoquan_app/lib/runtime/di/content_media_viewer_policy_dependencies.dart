import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_media_viewer_policy.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';

final contentMediaViewerPolicyProvider = Provider<ContentMediaViewerPolicy>(
  (ref) => const _MetadataContentMediaViewerPolicy(),
);

final class _MetadataContentMediaViewerPolicy
    implements ContentMediaViewerPolicy {
  const _MetadataContentMediaViewerPolicy();

  @override
  String get articleDarkPaperDefaultTheme =>
      ContentUIConfig.articleDarkPaperDefaultTheme;

  @override
  List<ContentMediaViewerPaperThemeOption> get articlePaperThemeOptions =>
      ContentUIConfig.articlePaperThemeOptions
          .map(
            (option) => ContentMediaViewerPaperThemeOption(
              id: option.id,
              labelKey: option.labelKey,
            ),
          )
          .toList(growable: false);

  @override
  List<ContentMediaViewerFilterOption> get workFormatFilters => ContentUIConfig
      .workFormatFilters
      .map(
        (filter) => ContentMediaViewerFilterOption(
          id: filter.id,
          labelKey: filter.labelKey,
          contentType: filter.contentType,
        ),
      )
      .toList(growable: false);
}
