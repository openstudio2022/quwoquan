import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageStatusReportView;

final class HomepageStatusReportDraft {
  const HomepageStatusReportDraft({
    required this.reason,
    this.description = '',
    this.evidenceUrls = const <String>[],
  });

  final String reason;
  final String description;
  final List<String> evidenceUrls;
}

/// HomepageStatusReport 对象的公开命令端口。
abstract interface class HomepageStatusReportCommandWriter {
  Future<HomepageStatusReportView> createStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  });
}
