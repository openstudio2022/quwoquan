import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class HomepageReviewCommandWriter {
  Future<HomepageReviewView> create(CreateHomepageReviewCommand command);

  Future<HomepageReviewView> update(UpdateHomepageReviewCommand command);

  Future<HomepageReviewView> delete(DeleteHomepageReviewCommand command);
}

abstract interface class HomepageReviewQuery {
  Future<HomepageReviewPageSlice> listByHomepage(HomepageReviewListQuery query);

  Future<HomepageReviewView> getMine(MyHomepageReviewQuery query);
}

/// Test adapter signal aligned with `ENTITY.USER.review_not_found`.
final class HomepageReviewNotFoundException implements Exception {
  const HomepageReviewNotFoundException();
}
