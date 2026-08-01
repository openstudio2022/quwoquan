// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../user/profile_update_proposal_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class ApplyProfileUpdateProposalCommand {
  ApplyProfileUpdateProposalCommand({
    required String proposalId,
  }) : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
  }

  final String proposalId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.proposalId,
  };
}

final class ConfirmProfileUpdateProposalCommand {
  ConfirmProfileUpdateProposalCommand({
    required String proposalId,
  }) : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
  }

  final String proposalId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.proposalId,
  };
}

final class CreateProfileUpdateProposalCommand {
  CreateProfileUpdateProposalCommand({
    required String personaId,
    required String proposalId,
    required ProfileUpdateProposalSource source,
    required ProfileChangeSet changes,
    required String reason,
    required List<String> evidenceRefs,
    required List<String> impactScope,
  }) : personaId = personaId.trim(),
       proposalId = proposalId.trim(),
       source = source,
       changes = changes,
       reason = reason.trim(),
       evidenceRefs = _normalizeGeneratedTextList(evidenceRefs, deduplicate: true),
       impactScope = _normalizeGeneratedTextList(impactScope, deduplicate: true) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String personaId;
  final String proposalId;
  final ProfileUpdateProposalSource source;
  final ProfileChangeSet changes;
  final String reason;
  final List<String> evidenceRefs;
  final List<String> impactScope;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    "proposalId": this.proposalId,
    "source": switch (this.source) { ProfileUpdateProposalSource.persona => "persona", ProfileUpdateProposalSource.assistant => "assistant", ProfileUpdateProposalSource.external => "external", },
    "changes": this.changes.toWire(),
    "reason": this.reason,
    "evidenceRefs": this.evidenceRefs.map((value) => value).toList(growable: false),
    "impactScope": this.impactScope.map((value) => value).toList(growable: false),
  };
}

final class ProfileUpdateProposalListQuery {
  ProfileUpdateProposalListQuery({
    required String personaId,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(this.personaId, "personaId", 'must not be blank');
    }
  }

  final String personaId;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "personaId": this.personaId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ProfileUpdateProposalQuery {
  ProfileUpdateProposalQuery({
    required String proposalId,
  }) : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
  }

  final String proposalId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.proposalId,
  };
}

final class RejectProfileUpdateProposalCommand {
  RejectProfileUpdateProposalCommand({
    required String proposalId,
  }) : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
  }

  final String proposalId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.proposalId,
  };
}

final class RollbackProfileUpdateProposalCommand {
  RollbackProfileUpdateProposalCommand({
    required String proposalId,
  }) : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(this.proposalId, "proposalId", 'must not be blank');
    }
  }

  final String proposalId;

  Map<String, Object?> toJson() => <String, Object?>{
    "id": this.proposalId,
  };
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalApplyProposalGeneratedRequest(ApplyProfileUpdateProposalCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.proposalId,
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalConfirmProposalGeneratedRequest(ConfirmProfileUpdateProposalCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.proposalId,
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalCreateProfileUpdateProposalGeneratedRequest(CreateProfileUpdateProposalCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    body: <String, Object?>{
      "proposalId": request.proposalId,
      "source": switch (request.source) { ProfileUpdateProposalSource.persona => "persona", ProfileUpdateProposalSource.assistant => "assistant", ProfileUpdateProposalSource.external => "external", },
      ...request.changes.toWire(),
      "reason": request.reason,
      "evidenceRefs": request.evidenceRefs.map((value) => value).toList(growable: false),
      "impactScope": request.impactScope.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalGetProfileUpdateProposalGeneratedRequest(ProfileUpdateProposalQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.proposalId,
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalListProfileUpdateProposalsGeneratedRequest(ProfileUpdateProposalListQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "personaId": request.personaId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalRejectProposalGeneratedRequest(RejectProfileUpdateProposalCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.proposalId,
    },
  );
}

CloudOperationRequestPayload encodeUserProfileUpdateProposalRollbackProposalGeneratedRequest(RollbackProfileUpdateProposalCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "id": request.proposalId,
    },
  );
}

