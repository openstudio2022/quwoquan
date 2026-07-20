import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test(
    'career and interest profile catalog comes from Audience user roots',
    () async {
      final repo = AlphaTagFacet();

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

      final validation = await repo.validateRefs(<String>[
        '${TagTaxonomyRefs.careerOccupationRoot}/产品运营/产品经理',
        '${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/旅行',
        'Topic/兴趣/旅行',
      ]);
      expect(
        validation.valid,
        contains('${TagTaxonomyRefs.careerInterestRoot}/旅行摄影/旅行'),
      );
      expect(validation.invalid, contains('Topic/兴趣/旅行'));
    },
  );
}
