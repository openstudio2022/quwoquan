// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/entity/homepage/service.yaml (writable_fields per operation).
// Regenerate: make codegen-app

Map<String, dynamic> _entityHomepageMutationPutOpt(Map<String, dynamic> m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

/// HTTP body for ReviewHomepageClaimRequest (metadata writable_fields).
class ReviewHomepageClaimRequestWire {
  ReviewHomepageClaimRequestWire({
    this.status,
    this.reviewNote,
  });

  final String? status;
  final String? reviewNote;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _entityHomepageMutationPutOpt(m, 'status', status);
    _entityHomepageMutationPutOpt(m, 'reviewNote', reviewNote);
    return m;
  }

  factory ReviewHomepageClaimRequestWire.fromMap(Map<String, dynamic> m) {
    return ReviewHomepageClaimRequestWire(
      status: m['status']?.toString(),
      reviewNote: m['reviewNote']?.toString(),
    );
  }
}

/// HTTP body for ReviewHomepageStatusReport (metadata writable_fields).
class ReviewHomepageStatusReportWire {
  ReviewHomepageStatusReportWire({
    this.status,
    this.reviewNote,
  });

  final String? status;
  final String? reviewNote;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _entityHomepageMutationPutOpt(m, 'status', status);
    _entityHomepageMutationPutOpt(m, 'reviewNote', reviewNote);
    return m;
  }

  factory ReviewHomepageStatusReportWire.fromMap(Map<String, dynamic> m) {
    return ReviewHomepageStatusReportWire(
      status: m['status']?.toString(),
      reviewNote: m['reviewNote']?.toString(),
    );
  }
}

/// HTTP body for PublishHomepageCandidate (metadata writable_fields).
class PublishHomepageCandidateWire {
  const PublishHomepageCandidateWire();

  Map<String, dynamic> toWire() => <String, dynamic>{};

  factory PublishHomepageCandidateWire.fromMap(Map<String, dynamic> m) => PublishHomepageCandidateWire();
}

