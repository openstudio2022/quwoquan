// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';

void main() {
  test(
    'career and interest profile catalog comes from Audience user roots',
    () async {
      final repo = AlphaTagFacet(
        taxonomyReleaseId:
            ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
      );

      final occupationCategories = await repo.listChildren(
        TagTaxonomyRefs.careerOccupationRoot,
      );
      expect(
        occupationCategories.map((child) => child.tagRef),
        containsAll(<String>[
          '${TagTaxonomyRefs.careerOccupationRoot}/产品运营',
          '${TagTaxonomyRefs.careerOccupationRoot}/研发技术',
          '${TagTaxonomyRefs.careerOccupationRoot}/学生',
        ]),
      );

      final productOps = await repo.listChildren(
        '${TagTaxonomyRefs.careerOccupationRoot}/产品运营',
      );
      expect(
        productOps.map((child) => child.tagRef),
        contains('${TagTaxonomyRefs.careerOccupationRoot}/产品运营/产品经理'),
      );

      final travelPhoto = await repo.listChildren(
        '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影',
      );
      expect(
        travelPhoto.map((child) => child.tagRef),
        containsAll(<String>[
          '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/旅行',
          '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/摄影',
          '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/城市漫游',
        ]),
      );

      final validation = await repo.validateRefs(
        expectedTaxonomyReleaseId:
            ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
        tagRefs: <String>[
          '${TagTaxonomyRefs.careerOccupationRoot}/产品运营/产品经理',
          '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/旅行',
          'Topic/兴趣/旅行',
        ],
      );
      expect(
        validation.taxonomyReleaseId,
        ContentUIConfig.onboardingInterestCatalog.taxonomyReleaseId,
      );
      expect(
        validation.valid,
        contains('${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/旅行'),
      );
      expect(validation.invalid, contains('Topic/兴趣/旅行'));
    },
  );
}
