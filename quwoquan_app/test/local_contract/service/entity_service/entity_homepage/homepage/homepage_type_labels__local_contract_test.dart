import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_type_labels.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

// spec_ref: specs/feature-tree/shared-homepage-network/spec.md#dom-001
void main() {
  test('canonical school homepage type uses its semantic label', () {
    expect(homepageTypeLabel('school'), CreationText.homepageTypeSchool);
  });

  test('undeclared homepage type keeps the generic fallback', () {
    expect(
      homepageTypeLabel('not_a_homepage_type'),
      ObjectHomepageText.homepageTypeDefault,
    );
  });
}
