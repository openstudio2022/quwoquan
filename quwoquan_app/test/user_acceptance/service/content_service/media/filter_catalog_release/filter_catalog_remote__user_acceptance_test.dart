// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-003
// readiness_case: filter_catalog_release_remote_app_uat

import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/filter_catalog_coordinator.dart';
import '../../../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../../../support/runtime/patrol/patrol_environment_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

void main() {
  patrolTest(
    'active Remote filter catalog reaches the real image editor surface',
    tags: const <String>['user-acceptance', 'content', 'filter-catalog'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      await launchEnvironmentPatrolApp($);
      final container = patrolMountedContainer();
      final resolved = await container
          .read(filterCatalogCoordinatorProvider)
          .load();
      expect(resolved.source, FilterCatalogSource.remote);
      expect(resolved.snapshot.releaseId, isNotEmpty);
      expect(resolved.snapshot.presets, isNotEmpty);
      final config = await container
          .read(imageEditorFilterRepositoryProvider)
          .loadConfig();
      expect(config.releaseId, resolved.snapshot.releaseId);
      expect(config.presets, isNotEmpty);

      final image = await _writeGeneratedImage();
      try {
        await patrolGoTo(
          $,
          AppRoutePaths.createEditImage(
            path: image.path,
            source: 'filterCatalogRemoteUat',
            index: '0',
            total: '1',
          ),
        );
        expect(
          await _waitFor($, find.text(MediaText.imageEditorFilter)),
          isTrue,
        );
        await $(MediaText.imageEditorFilter).tap();
        final visiblePreset = config.presets.firstWhere(
          (preset) => preset.enabled,
        );
        expect(
          await _waitFor($, find.text(visiblePreset.name)),
          isTrue,
          reason:
              'Remote active release preset must render on the editor surface',
        );
        expect(find.text(MediaText.imageEditorFilterLoadFailed), findsNothing);
      } finally {
        await image.parent.delete(recursive: true);
      }
    },
  );
}

Future<File> _writeGeneratedImage() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    const Rect.fromLTWH(0, 0, 64, 64),
    Paint()..color = const Color(0xff3366cc),
  );
  final image = await recorder.endRecording().toImage(64, 64);
  final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  if (bytes == null) throw StateError('failed to encode generated UAT image');
  final directory = await Directory.systemTemp.createTemp('qwq-filter-uat-');
  return File('${directory.path}/generated.png')
    ..writeAsBytesSync(bytes.buffer.asUint8List(), flush: true);
}

Future<bool> _waitFor(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump();
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
