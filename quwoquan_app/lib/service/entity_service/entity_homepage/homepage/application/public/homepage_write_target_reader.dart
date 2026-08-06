/// 认领与状态上报页面所需的最小主页读取投影。
final class HomepageWriteTarget {
  const HomepageWriteTarget({
    required this.homepageId,
    required this.title,
    required this.status,
    this.claimStatus,
  });

  final String homepageId;
  final String title;
  final String status;
  final String? claimStatus;
}

/// Homepage 对象提供给写入参与对象的公开读取端口。
abstract interface class HomepageWriteTargetReader {
  Future<HomepageWriteTarget> getHomepageWriteTarget(String homepageId);
}
