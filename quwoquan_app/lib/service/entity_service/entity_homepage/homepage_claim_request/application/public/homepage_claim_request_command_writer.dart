import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageClaimRequestView;

final class HomepageClaimRequestDraft {
  const HomepageClaimRequestDraft({
    required this.claimTier,
    required this.contactPhone,
    this.businessLicenseUrl = '',
    this.identityCardFrontUrl = '',
    this.identityCardBackUrl = '',
    this.note = '',
  });

  final String claimTier;
  final String contactPhone;
  final String businessLicenseUrl;
  final String identityCardFrontUrl;
  final String identityCardBackUrl;
  final String note;
}

/// HomepageClaimRequest 对象的公开命令端口。
abstract interface class HomepageClaimRequestCommandWriter {
  Future<HomepageClaimRequestView> createClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  });
}
