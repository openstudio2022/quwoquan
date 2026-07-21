part of 'entity_repository.dart';

abstract interface class HomepageIntroductionRepository {
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  });
}

/// 将 pure-contract 介绍页投影为 App DTO；不绑定 Remote 或 alpha 实现。
class HomepageIntroductionProjectionAdapter
    implements HomepageIntroductionRepository {
  HomepageIntroductionProjectionAdapter({required this.query});

  final HomepageIntroductionQuery query;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    return homepageIntroductionFromContract(
      await query.getHomepageIntroduction(
        homepageId,
        cancellation: cancellation,
      ),
    );
  }
}
