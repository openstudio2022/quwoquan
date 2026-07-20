part of 'entity_repository.dart';

abstract class HomepageIntroductionRepository {
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  });
}

class RemoteHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  RemoteHomepageIntroductionRepository({required this.queryAdapter});

  final RemoteHomepageQueryAdapter queryAdapter;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    return homepageIntroductionFromContract(
      await queryAdapter.getHomepageIntroduction(
        homepageId,
        cancellation: cancellation,
      ),
    );
  }
}
