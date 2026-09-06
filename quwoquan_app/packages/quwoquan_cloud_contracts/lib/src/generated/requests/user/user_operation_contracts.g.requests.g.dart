// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 157736ecc8566df93f4bf80645e3060c065d845c9dd2af2b8186447883b0206f

part of '../../../user/user_operation_contracts.g.dart';

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

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}

void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}

DateTime _generatedRequestTimestamp(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a timestamp');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be a timestamp');
  return parsed.toUtc();
}

List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class ActivatePersonaCommand {
  ActivatePersonaCommand({required String personaId})
    : personaId = personaId.trim() {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
  }

  final String personaId;

  factory ActivatePersonaCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ActivatePersonaCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return ActivatePersonaCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class ApplyPersonaProfileSyncCommand {
  ApplyPersonaProfileSyncCommand({
    required String personaId,
    required String applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : personaId = personaId.trim(),
       applyScope = applyScope.trim(),
       syncTargetIds = syncTargetIds == null
           ? null
           : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.applyScope.isEmpty) {
      throw ArgumentError.value(
        this.applyScope,
        "applyScope",
        'must not be blank',
      );
    }
  }

  final String personaId;
  final String applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  factory ApplyPersonaProfileSyncCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ApplyPersonaProfileSyncCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "applyScope",
      "syncTargetIds",
      "fieldsMask",
    }, path);
    return ApplyPersonaProfileSyncCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      applyScope: _generatedRequestString(
        map["applyScope"],
        '$path.applyScope',
      ),
      syncTargetIds: map["syncTargetIds"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["syncTargetIds"],
                '$path.syncTargetIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.syncTargetIds' + '[${entry.key}]',
                ),
              ),
            ),
      fieldsMask: map["fieldsMask"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["fieldsMask"],
                '$path.fieldsMask',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.fieldsMask' + '[${entry.key}]',
                ),
              ),
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "applyScope": this.applyScope,
    if (this.syncTargetIds != null)
      "syncTargetIds": this.syncTargetIds!
          .map((value) => value)
          .toList(growable: false),
    if (this.fieldsMask != null)
      "fieldsMask": this.fieldsMask!
          .map((value) => value)
          .toList(growable: false),
  };
}

final class ApplyProfileUpdateProposalCommand {
  ApplyProfileUpdateProposalCommand({required String proposalId})
    : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
  }

  final String proposalId;

  factory ApplyProfileUpdateProposalCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ApplyProfileUpdateProposalCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return ApplyProfileUpdateProposalCommand(
      proposalId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.proposalId};
}

final class BindCarrierPhoneCredentialCommand {
  BindCarrierPhoneCredentialCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? displayLabel,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       displayLabel = displayLabel {
    if (this.vendor.isEmpty) {
      throw ArgumentError.value(this.vendor, "vendor", 'must not be blank');
    }
    if (this.carrierToken.isEmpty) {
      throw ArgumentError.value(
        this.carrierToken,
        "carrierToken",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
  }

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? displayLabel;

  factory BindCarrierPhoneCredentialCommand.fromWire(
    Map<String, Object?> map, [
    String path = "BindCarrierPhoneCredentialCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "vendor",
      "carrierToken",
      "deviceId",
      "platform",
      "displayLabel",
    }, path);
    return BindCarrierPhoneCredentialCommand(
      vendor: _generatedRequestString(map["vendor"], '$path.vendor'),
      carrierToken: _generatedRequestString(
        map["carrierToken"],
        '$path.carrierToken',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      displayLabel: map["displayLabel"] == null
          ? null
          : _generatedRequestString(map["displayLabel"], '$path.displayLabel'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.displayLabel != null) "displayLabel": this.displayLabel!,
  };
}

final class BindPhoneCredentialCommand {
  BindPhoneCredentialCommand({
    required String phone,
    required String otpCode,
    String? displayLabel,
  }) : phone = phone.trim(),
       otpCode = otpCode.trim(),
       displayLabel = displayLabel {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
    }
  }

  final String phone;
  final String otpCode;
  final String? displayLabel;

  factory BindPhoneCredentialCommand.fromWire(
    Map<String, Object?> map, [
    String path = "BindPhoneCredentialCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "phone",
      "otpCode",
      "displayLabel",
    }, path);
    return BindPhoneCredentialCommand(
      phone: _generatedRequestString(map["phone"], '$path.phone'),
      otpCode: _generatedRequestString(map["otpCode"], '$path.otpCode'),
      displayLabel: map["displayLabel"] == null
          ? null
          : _generatedRequestString(map["displayLabel"], '$path.displayLabel'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "phone": this.phone,
    "otpCode": this.otpCode,
    if (this.displayLabel != null) "displayLabel": this.displayLabel!,
  };
}

final class BlockUserCommand {
  BlockUserCommand({required String targetPersonaId})
    : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
  }

  final String targetPersonaId;

  factory BlockUserCommand.fromWire(
    Map<String, Object?> map, [
    String path = "BlockUserCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetPersonaId",
    }, path);
    return BlockUserCommand(
      targetPersonaId: _generatedRequestString(
        map["targetPersonaId"],
        '$path.targetPersonaId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
  };
}

final class CancelGreetingCommand {
  CancelGreetingCommand({required String requestId})
    : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(
        this.requestId,
        "requestId",
        'must not be blank',
      );
    }
  }

  final String requestId;

  factory CancelGreetingCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CancelGreetingCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "requestId",
    }, path);
    return CancelGreetingCommand(
      requestId: _generatedRequestString(map["requestId"], '$path.requestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class CloseAccountCommand {
  const CloseAccountCommand({String? clientRequestId})
    : clientRequestId = clientRequestId;

  final String? clientRequestId;

  factory CloseAccountCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CloseAccountCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "clientRequestId",
    }, path);
    return CloseAccountCommand(
      clientRequestId: map["clientRequestId"] == null
          ? null
          : _generatedRequestString(
              map["clientRequestId"],
              '$path.clientRequestId',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.clientRequestId != null) "clientRequestId": this.clientRequestId!,
  };
}

final class CompleteFederatedPhoneBindingCommand {
  CompleteFederatedPhoneBindingCommand({
    required String bindingTicket,
    required String phone,
    required String otpCode,
    required String challengeId,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : bindingTicket = bindingTicket.trim(),
       phone = phone.trim(),
       otpCode = otpCode.trim(),
       challengeId = challengeId.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim(),
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.bindingTicket.isEmpty) {
      throw ArgumentError.value(
        this.bindingTicket,
        "bindingTicket",
        'must not be blank',
      );
    }
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
    }
    if (this.challengeId.isEmpty) {
      throw ArgumentError.value(
        this.challengeId,
        "challengeId",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(
        this.appVersion,
        "appVersion",
        'must not be blank',
      );
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String bindingTicket;
  final String phone;
  final String otpCode;
  final String challengeId;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory CompleteFederatedPhoneBindingCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CompleteFederatedPhoneBindingCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "bindingTicket",
      "phone",
      "otpCode",
      "challengeId",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return CompleteFederatedPhoneBindingCommand(
      bindingTicket: _generatedRequestString(
        map["bindingTicket"],
        '$path.bindingTicket',
      ),
      phone: _generatedRequestString(map["phone"], '$path.phone'),
      otpCode: _generatedRequestString(map["otpCode"], '$path.otpCode'),
      challengeId: _generatedRequestString(
        map["challengeId"],
        '$path.challengeId',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: _generatedRequestString(
        map["appVersion"],
        '$path.appVersion',
      ),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "bindingTicket": this.bindingTicket,
    "phone": this.phone,
    "otpCode": this.otpCode,
    "challengeId": this.challengeId,
    "deviceId": this.deviceId,
    "platform": this.platform,
    "appVersion": this.appVersion,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class ConfirmProfileUpdateProposalCommand {
  ConfirmProfileUpdateProposalCommand({required String proposalId})
    : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
  }

  final String proposalId;

  factory ConfirmProfileUpdateProposalCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ConfirmProfileUpdateProposalCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return ConfirmProfileUpdateProposalCommand(
      proposalId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.proposalId};
}

final class CreateAlipayAuthorizationRequestCommand {
  const CreateAlipayAuthorizationRequestCommand({
    String? platform,
    String? appVersion,
  }) : platform = platform,
       appVersion = appVersion;

  final String? platform;
  final String? appVersion;

  factory CreateAlipayAuthorizationRequestCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateAlipayAuthorizationRequestCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "platform",
      "appVersion",
    }, path);
    return CreateAlipayAuthorizationRequestCommand(
      platform: map["platform"] == null
          ? null
          : _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.platform != null) "platform": this.platform!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
  };
}

final class CreatePersonaCommand {
  CreatePersonaCommand({
    required String displayName,
    String? avatarUrl,
    String? isolationLevel,
    String? purposeHint,
  }) : displayName = displayName.trim(),
       avatarUrl = avatarUrl,
       isolationLevel = isolationLevel,
       purposeHint = purposeHint {
    if (this.displayName.isEmpty) {
      throw ArgumentError.value(
        this.displayName,
        "displayName",
        'must not be blank',
      );
    }
  }

  final String displayName;
  final String? avatarUrl;
  final String? isolationLevel;
  final String? purposeHint;

  factory CreatePersonaCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreatePersonaCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "displayName",
      "avatarUrl",
      "isolationLevel",
      "purposeHint",
    }, path);
    return CreatePersonaCommand(
      displayName: _generatedRequestString(
        map["displayName"],
        '$path.displayName',
      ),
      avatarUrl: map["avatarUrl"] == null
          ? null
          : _generatedRequestString(map["avatarUrl"], '$path.avatarUrl'),
      isolationLevel: map["isolationLevel"] == null
          ? null
          : _generatedRequestString(
              map["isolationLevel"],
              '$path.isolationLevel',
            ),
      purposeHint: map["purposeHint"] == null
          ? null
          : _generatedRequestString(map["purposeHint"], '$path.purposeHint'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "displayName": this.displayName,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.isolationLevel != null) "isolationLevel": this.isolationLevel!,
    if (this.purposeHint != null) "purposeHint": this.purposeHint!,
  };
}

final class CreateProfileUpdateProposalCommand {
  CreateProfileUpdateProposalCommand({
    required String personaId,
    required String proposalId,
    required ProposalSource source,
    String? displayName,
    String? bio,
    String? avatarMediaAssetId,
    String? backgroundMediaAssetId,
    bool? isPrivate,
    String? isolationLevel,
    String? purposeHint,
    required String reason,
    required List<String> evidenceRefs,
    required List<String> impactScope,
  }) : personaId = personaId.trim(),
       proposalId = proposalId.trim(),
       source = source,
       displayName = displayName,
       bio = bio,
       avatarMediaAssetId = avatarMediaAssetId,
       backgroundMediaAssetId = backgroundMediaAssetId,
       isPrivate = isPrivate,
       isolationLevel = isolationLevel,
       purposeHint = purposeHint,
       reason = reason.trim(),
       evidenceRefs = _normalizeGeneratedTextList(
         evidenceRefs,
         deduplicate: true,
       ),
       impactScope = _normalizeGeneratedTextList(
         impactScope,
         deduplicate: true,
       ) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
    if (this.displayName != null && this.displayName!.length > 64) {
      throw ArgumentError.value(
        this.displayName,
        "displayName",
        "length exceeds 64",
      );
    }
    if (this.bio != null && this.bio!.length > 500) {
      throw ArgumentError.value(this.bio, "bio", "length exceeds 500");
    }
    if (this.purposeHint != null && this.purposeHint!.length > 120) {
      throw ArgumentError.value(
        this.purposeHint,
        "purposeHint",
        "length exceeds 120",
      );
    }
    if (this.reason.isEmpty) {
      throw ArgumentError.value(this.reason, "reason", 'must not be blank');
    }
  }

  final String personaId;
  final String proposalId;
  final ProposalSource source;
  final String? displayName;
  final String? bio;
  final String? avatarMediaAssetId;
  final String? backgroundMediaAssetId;
  final bool? isPrivate;
  final String? isolationLevel;
  final String? purposeHint;
  final String reason;
  final List<String> evidenceRefs;
  final List<String> impactScope;

  factory CreateProfileUpdateProposalCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateProfileUpdateProposalCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "proposalId",
      "source",
      "displayName",
      "bio",
      "avatarMediaAssetId",
      "backgroundMediaAssetId",
      "isPrivate",
      "isolationLevel",
      "purposeHint",
      "reason",
      "evidenceRefs",
      "impactScope",
    }, path);
    return CreateProfileUpdateProposalCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      proposalId: _generatedRequestString(
        map["proposalId"],
        '$path.proposalId',
      ),
      source: switch (map["source"]) {
        "persona" => ProposalSource.persona,
        "assistant" => ProposalSource.assistant,
        "external" => ProposalSource.external,
        _ => throw FormatException(
          '$path.source' + ' has an invalid enum value',
        ),
      },
      displayName: map["displayName"] == null
          ? null
          : _generatedRequestString(map["displayName"], '$path.displayName'),
      bio: map["bio"] == null
          ? null
          : _generatedRequestString(map["bio"], '$path.bio'),
      avatarMediaAssetId: map["avatarMediaAssetId"] == null
          ? null
          : _generatedRequestString(
              map["avatarMediaAssetId"],
              '$path.avatarMediaAssetId',
            ),
      backgroundMediaAssetId: map["backgroundMediaAssetId"] == null
          ? null
          : _generatedRequestString(
              map["backgroundMediaAssetId"],
              '$path.backgroundMediaAssetId',
            ),
      isPrivate: map["isPrivate"] == null
          ? null
          : _generatedRequestBool(map["isPrivate"], '$path.isPrivate'),
      isolationLevel: map["isolationLevel"] == null
          ? null
          : _generatedRequestString(
              map["isolationLevel"],
              '$path.isolationLevel',
            ),
      purposeHint: map["purposeHint"] == null
          ? null
          : _generatedRequestString(map["purposeHint"], '$path.purposeHint'),
      reason: _generatedRequestString(map["reason"], '$path.reason'),
      evidenceRefs: List<String>.unmodifiable(
        _generatedRequestList(
          map["evidenceRefs"],
          '$path.evidenceRefs',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.evidenceRefs' + '[${entry.key}]',
          ),
        ),
      ),
      impactScope: List<String>.unmodifiable(
        _generatedRequestList(
          map["impactScope"],
          '$path.impactScope',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.impactScope' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    "proposalId": this.proposalId,
    "source": this.source.wireName,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.bio != null) "bio": this.bio!,
    if (this.avatarMediaAssetId != null)
      "avatarMediaAssetId": this.avatarMediaAssetId!,
    if (this.backgroundMediaAssetId != null)
      "backgroundMediaAssetId": this.backgroundMediaAssetId!,
    if (this.isPrivate != null) "isPrivate": this.isPrivate!,
    if (this.isolationLevel != null) "isolationLevel": this.isolationLevel!,
    if (this.purposeHint != null) "purposeHint": this.purposeHint!,
    "reason": this.reason,
    "evidenceRefs": this.evidenceRefs
        .map((value) => value)
        .toList(growable: false),
    "impactScope": this.impactScope
        .map((value) => value)
        .toList(growable: false),
  };
}

final class DevicePushEndpointRemoveCommand {
  DevicePushEndpointRemoveCommand({
    required String deviceId,
    required DevicePushEndpointKind endpointKind,
  }) : deviceId = deviceId.trim(),
       endpointKind = endpointKind {
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
  }

  final String deviceId;
  final DevicePushEndpointKind endpointKind;

  factory DevicePushEndpointRemoveCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DevicePushEndpointRemoveCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "deviceId",
      "endpointKind",
    }, path);
    return DevicePushEndpointRemoveCommand(
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      endpointKind: switch (map["endpointKind"]) {
        "apns_voip" => DevicePushEndpointKind.apnsVoip,
        "fcm" => DevicePushEndpointKind.fcm,
        _ => throw FormatException(
          '$path.endpointKind' + ' has an invalid enum value',
        ),
      },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "deviceId": this.deviceId,
    "endpointKind": this.endpointKind.wireName,
  };
}

final class DevicePushEndpointUpsertCommand {
  DevicePushEndpointUpsertCommand({
    required String deviceId,
    required DevicePushEndpointKind endpointKind,
    required String token,
    required String appVersion,
  }) : deviceId = deviceId.trim(),
       endpointKind = endpointKind,
       token = token.trim(),
       appVersion = appVersion.trim() {
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.token.isEmpty) {
      throw ArgumentError.value(this.token, "token", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(
        this.appVersion,
        "appVersion",
        'must not be blank',
      );
    }
  }

  final String deviceId;
  final DevicePushEndpointKind endpointKind;
  final String token;
  final String appVersion;

  factory DevicePushEndpointUpsertCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DevicePushEndpointUpsertCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "deviceId",
      "endpointKind",
      "token",
      "appVersion",
    }, path);
    return DevicePushEndpointUpsertCommand(
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      endpointKind: switch (map["endpointKind"]) {
        "apns_voip" => DevicePushEndpointKind.apnsVoip,
        "fcm" => DevicePushEndpointKind.fcm,
        _ => throw FormatException(
          '$path.endpointKind' + ' has an invalid enum value',
        ),
      },
      token: _generatedRequestString(map["token"], '$path.token'),
      appVersion: _generatedRequestString(
        map["appVersion"],
        '$path.appVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "deviceId": this.deviceId,
    "endpointKind": this.endpointKind.wireName,
    "token": this.token,
    "appVersion": this.appVersion,
  };
}

final class DismissContactDiscoveryCommand {
  DismissContactDiscoveryCommand({required String discoveryId})
    : discoveryId = discoveryId.trim() {
    if (this.discoveryId.isEmpty) {
      throw ArgumentError.value(
        this.discoveryId,
        "discoveryId",
        'must not be blank',
      );
    }
  }

  final String discoveryId;

  factory DismissContactDiscoveryCommand.fromWire(
    Map<String, Object?> map, [
    String path = "DismissContactDiscoveryCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return DismissContactDiscoveryCommand(
      discoveryId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.discoveryId};
}

final class FollowSubjectCommand {
  FollowSubjectCommand({
    required SubjectFollowTargetKind subjectType,
    required String subjectId,
    String? source,
  }) : subjectType = subjectType,
       subjectId = subjectId.trim(),
       source = _normalizeGeneratedOptionalText(source) {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(
        this.subjectId,
        "subjectId",
        'must not be blank',
      );
    }
  }

  final SubjectFollowTargetKind subjectType;
  final String subjectId;
  final String? source;

  factory FollowSubjectCommand.fromWire(
    Map<String, Object?> map, [
    String path = "FollowSubjectCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "subjectType",
      "subjectId",
      "source",
    }, path);
    return FollowSubjectCommand(
      subjectType: switch (map["subjectType"]) {
        "homepage" => SubjectFollowTargetKind.homepage,
        "circle" => SubjectFollowTargetKind.circle,
        "location" => SubjectFollowTargetKind.location,
        _ => throw FormatException(
          '$path.subjectType' + ' has an invalid enum value',
        ),
      },
      subjectId: _generatedRequestString(map["subjectId"], '$path.subjectId'),
      source: map["source"] == null
          ? null
          : _generatedRequestString(map["source"], '$path.source'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectType": this.subjectType.wireName,
    "subjectId": this.subjectId,
    if (this.source != null) "source": this.source!,
  };
}

final class FollowUserCommand {
  FollowUserCommand({
    required String targetPersonaId,
    String? source,
    String? clientRequestId,
  }) : targetPersonaId = targetPersonaId.trim(),
       source = source,
       clientRequestId = clientRequestId {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
  }

  final String targetPersonaId;
  final String? source;
  final String? clientRequestId;

  factory FollowUserCommand.fromWire(
    Map<String, Object?> map, [
    String path = "FollowUserCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetPersonaId",
      "source",
      "clientRequestId",
    }, path);
    return FollowUserCommand(
      targetPersonaId: _generatedRequestString(
        map["targetPersonaId"],
        '$path.targetPersonaId',
      ),
      source: map["source"] == null
          ? null
          : _generatedRequestString(map["source"], '$path.source'),
      clientRequestId: map["clientRequestId"] == null
          ? null
          : _generatedRequestString(
              map["clientRequestId"],
              '$path.clientRequestId',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.source?.isNotEmpty == true) "source": this.source!,
    if (this.clientRequestId?.isNotEmpty == true)
      "clientRequestId": this.clientRequestId!,
  };
}

final class GetActivePersonaContextQuery {
  const GetActivePersonaContextQuery();
}

final class GetLatestContactDiscoveryQuery {
  const GetLatestContactDiscoveryQuery();
}

final class GetMeProfileQuery {
  const GetMeProfileQuery();
}

final class GetPersonaLifecycleGuardQuery {
  const GetPersonaLifecycleGuardQuery({required String personaId})
    : personaId = personaId;

  final String personaId;

  factory GetPersonaLifecycleGuardQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetPersonaLifecycleGuardQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return GetPersonaLifecycleGuardQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class GetPersonaManagementSummaryQuery {
  const GetPersonaManagementSummaryQuery();
}

final class GetPersonaProfileQuery {
  const GetPersonaProfileQuery({required String personaId})
    : personaId = personaId;

  final String personaId;

  factory GetPersonaProfileQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetPersonaProfileQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return GetPersonaProfileQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class GetProfileEditSnapshotQuery {
  const GetProfileEditSnapshotQuery();
}

final class GetProfileQrCardQuery {
  const GetProfileQrCardQuery();
}

final class GetRelationshipCapabilityQuery {
  GetRelationshipCapabilityQuery({required String targetPersonaId})
    : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
  }

  final String targetPersonaId;

  factory GetRelationshipCapabilityQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetRelationshipCapabilityQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return GetRelationshipCapabilityQuery(
      targetPersonaId: _generatedRequestString(
        map["personaId"],
        '$path.personaId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.targetPersonaId,
  };
}

final class GetUserHomepageBundleQuery {
  const GetUserHomepageBundleQuery({required String personaId})
    : personaId = personaId;

  final String personaId;

  factory GetUserHomepageBundleQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetUserHomepageBundleQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return GetUserHomepageBundleQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class IgnoreGreetingCommand {
  IgnoreGreetingCommand({required String requestId})
    : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(
        this.requestId,
        "requestId",
        'must not be blank',
      );
    }
  }

  final String requestId;

  factory IgnoreGreetingCommand.fromWire(
    Map<String, Object?> map, [
    String path = "IgnoreGreetingCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "requestId",
    }, path);
    return IgnoreGreetingCommand(
      requestId: _generatedRequestString(map["requestId"], '$path.requestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class InitiateContactDiscoveryCommand {
  InitiateContactDiscoveryCommand({required List<String> hashedPhones})
    : hashedPhones = _normalizeGeneratedTextList(
        hashedPhones,
        deduplicate: false,
      ) {}

  final List<String> hashedPhones;

  factory InitiateContactDiscoveryCommand.fromWire(
    Map<String, Object?> map, [
    String path = "InitiateContactDiscoveryCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "hashedPhones",
    }, path);
    return InitiateContactDiscoveryCommand(
      hashedPhones: List<String>.unmodifiable(
        _generatedRequestList(
          map["hashedPhones"],
          '$path.hashedPhones',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.hashedPhones' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "hashedPhones": this.hashedPhones
        .map((value) => value)
        .toList(growable: false),
  };
}

final class IssueWhitelistedResearchSessionCommand {
  const IssueWhitelistedResearchSessionCommand();
}

final class ListBlockedUsersQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ListBlockedUsersQuery({String? cursor, int limit = 20})
    : cursor = cursor,
      limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;

  factory ListBlockedUsersQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListBlockedUsersQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "cursor",
      "limit",
    }, path);
    return ListBlockedUsersQuery(
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ListCredentialsQuery {
  const ListCredentialsQuery();
}

final class ListFollowingSubjectsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ListFollowingSubjectsQuery({
    String? cursor,
    int limit = 20,
    FollowSubjectKind? subjectType,
  }) : cursor = cursor,
       limit = limit,
       subjectType = subjectType {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;
  final FollowSubjectKind? subjectType;

  factory ListFollowingSubjectsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListFollowingSubjectsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "cursor",
      "limit",
      "subjectType",
    }, path);
    return ListFollowingSubjectsQuery(
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
      subjectType: map["subjectType"] == null
          ? null
          : switch (map["subjectType"]) {
              "persona" => FollowSubjectKind.persona,
              "homepage" => FollowSubjectKind.homepage,
              "circle" => FollowSubjectKind.circle,
              "location" => FollowSubjectKind.location,
              _ => throw FormatException(
                '$path.subjectType' + ' has an invalid enum value',
              ),
            },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.subjectType != null) "subjectType": this.subjectType!.wireName,
  };
}

final class ListGreetingRequestsQuery {
  const ListGreetingRequestsQuery({
    String status = 'pending',
    String? cursor,
    int limit = 20,
  }) : status = status,
       cursor = cursor,
       limit = limit;

  final String status;
  final String? cursor;
  final int limit;

  factory ListGreetingRequestsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListGreetingRequestsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "status",
      "cursor",
      "limit",
    }, path);
    return ListGreetingRequestsQuery(
      status: map.containsKey("status")
          ? _generatedRequestString(map["status"], '$path.status')
          : 'pending',
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.status.isNotEmpty) "status": this.status,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ListPersonasQuery {
  const ListPersonasQuery();
}

final class LoginAnonymousCommand {
  LoginAnonymousCommand({
    required String installId,
    required String deviceFingerprintHash,
    required String platform,
    required String appVersion,
  }) : installId = installId.trim(),
       deviceFingerprintHash = deviceFingerprintHash.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim() {
    if (this.installId.isEmpty) {
      throw ArgumentError.value(
        this.installId,
        "installId",
        'must not be blank',
      );
    }
    if (this.deviceFingerprintHash.isEmpty) {
      throw ArgumentError.value(
        this.deviceFingerprintHash,
        "deviceFingerprintHash",
        'must not be blank',
      );
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(
        this.appVersion,
        "appVersion",
        'must not be blank',
      );
    }
  }

  final String installId;
  final String deviceFingerprintHash;
  final String platform;
  final String appVersion;

  factory LoginAnonymousCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginAnonymousCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "installId",
      "deviceFingerprintHash",
      "platform",
      "appVersion",
    }, path);
    return LoginAnonymousCommand(
      installId: _generatedRequestString(map["installId"], '$path.installId'),
      deviceFingerprintHash: _generatedRequestString(
        map["deviceFingerprintHash"],
        '$path.deviceFingerprintHash',
      ),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: _generatedRequestString(
        map["appVersion"],
        '$path.appVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "installId": this.installId,
    "deviceFingerprintHash": this.deviceFingerprintHash,
    "platform": this.platform,
    "appVersion": this.appVersion,
  };
}

final class LoginOneTapCommand {
  LoginOneTapCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.vendor.isEmpty) {
      throw ArgumentError.value(this.vendor, "vendor", 'must not be blank');
    }
    if (this.carrierToken.isEmpty) {
      throw ArgumentError.value(
        this.carrierToken,
        "carrierToken",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory LoginOneTapCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginOneTapCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "vendor",
      "carrierToken",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return LoginOneTapCommand(
      vendor: _generatedRequestString(map["vendor"], '$path.vendor'),
      carrierToken: _generatedRequestString(
        map["carrierToken"],
        '$path.carrierToken',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithAlipayCommand {
  LoginWithAlipayCommand({
    required String alipayAuthCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : alipayAuthCode = alipayAuthCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.alipayAuthCode.isEmpty) {
      throw ArgumentError.value(
        this.alipayAuthCode,
        "alipayAuthCode",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String alipayAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory LoginWithAlipayCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginWithAlipayCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "alipayAuthCode",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return LoginWithAlipayCommand(
      alipayAuthCode: _generatedRequestString(
        map["alipayAuthCode"],
        '$path.alipayAuthCode',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "alipayAuthCode": this.alipayAuthCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithPhoneCommand {
  LoginWithPhoneCommand({
    required String phone,
    required String otpCode,
    required String deviceId,
    required String platform,
    required String appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : phone = phone.trim(),
       otpCode = otpCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion.trim(),
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
    if (this.otpCode.isEmpty) {
      throw ArgumentError.value(this.otpCode, "otpCode", 'must not be blank');
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(
        this.appVersion,
        "appVersion",
        'must not be blank',
      );
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String phone;
  final String otpCode;
  final String deviceId;
  final String platform;
  final String appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory LoginWithPhoneCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginWithPhoneCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "phone",
      "otpCode",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return LoginWithPhoneCommand(
      phone: _generatedRequestString(map["phone"], '$path.phone'),
      otpCode: _generatedRequestString(map["otpCode"], '$path.otpCode'),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: _generatedRequestString(
        map["appVersion"],
        '$path.appVersion',
      ),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "phone": this.phone,
    "otpCode": this.otpCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    "appVersion": this.appVersion,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithQqCommand {
  LoginWithQqCommand({
    required String qqAuthCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : qqAuthCode = qqAuthCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.qqAuthCode.isEmpty) {
      throw ArgumentError.value(
        this.qqAuthCode,
        "qqAuthCode",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String qqAuthCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory LoginWithQqCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginWithQqCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "qqAuthCode",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return LoginWithQqCommand(
      qqAuthCode: _generatedRequestString(
        map["qqAuthCode"],
        '$path.qqAuthCode',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "qqAuthCode": this.qqAuthCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LoginWithWechatCommand {
  LoginWithWechatCommand({
    required String wechatCode,
    required String deviceId,
    required String platform,
    String? appVersion,
    required String agreementVersion,
    required String privacyVersion,
  }) : wechatCode = wechatCode.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion,
       agreementVersion = agreementVersion.trim(),
       privacyVersion = privacyVersion.trim() {
    if (this.wechatCode.isEmpty) {
      throw ArgumentError.value(
        this.wechatCode,
        "wechatCode",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.agreementVersion.isEmpty) {
      throw ArgumentError.value(
        this.agreementVersion,
        "agreementVersion",
        'must not be blank',
      );
    }
    if (this.privacyVersion.isEmpty) {
      throw ArgumentError.value(
        this.privacyVersion,
        "privacyVersion",
        'must not be blank',
      );
    }
  }

  final String wechatCode;
  final String deviceId;
  final String platform;
  final String? appVersion;
  final String agreementVersion;
  final String privacyVersion;

  factory LoginWithWechatCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LoginWithWechatCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "wechatCode",
      "deviceId",
      "platform",
      "appVersion",
      "agreementVersion",
      "privacyVersion",
    }, path);
    return LoginWithWechatCommand(
      wechatCode: _generatedRequestString(
        map["wechatCode"],
        '$path.wechatCode',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      agreementVersion: _generatedRequestString(
        map["agreementVersion"],
        '$path.agreementVersion',
      ),
      privacyVersion: _generatedRequestString(
        map["privacyVersion"],
        '$path.privacyVersion',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "wechatCode": this.wechatCode,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    "agreementVersion": this.agreementVersion,
    "privacyVersion": this.privacyVersion,
  };
}

final class LogoutCommand {
  const LogoutCommand({String? refreshToken, String? deviceId})
    : refreshToken = refreshToken,
      deviceId = deviceId;

  final String? refreshToken;
  final String? deviceId;

  factory LogoutCommand.fromWire(
    Map<String, Object?> map, [
    String path = "LogoutCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "refreshToken",
      "deviceId",
    }, path);
    return LogoutCommand(
      refreshToken: map["refreshToken"] == null
          ? null
          : _generatedRequestString(map["refreshToken"], '$path.refreshToken'),
      deviceId: map["deviceId"] == null
          ? null
          : _generatedRequestString(map["deviceId"], '$path.deviceId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.refreshToken != null) "refreshToken": this.refreshToken!,
    if (this.deviceId != null) "deviceId": this.deviceId!,
  };
}

final class MarkFollowedSubjectVisitedCommand {
  MarkFollowedSubjectVisitedCommand({
    required String subjectId,
    required FollowSubjectKind subjectType,
    required DateTime visitedAt,
    String? clientRequestId,
  }) : subjectId = subjectId.trim(),
       subjectType = subjectType,
       visitedAt = visitedAt,
       clientRequestId = _normalizeGeneratedOptionalText(clientRequestId) {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(
        this.subjectId,
        "subjectId",
        'must not be blank',
      );
    }
  }

  final String subjectId;
  final FollowSubjectKind subjectType;
  final DateTime visitedAt;
  final String? clientRequestId;

  factory MarkFollowedSubjectVisitedCommand.fromWire(
    Map<String, Object?> map, [
    String path = "MarkFollowedSubjectVisitedCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "subjectId",
      "subjectType",
      "visitedAt",
      "clientRequestId",
    }, path);
    return MarkFollowedSubjectVisitedCommand(
      subjectId: _generatedRequestString(map["subjectId"], '$path.subjectId'),
      subjectType: switch (map["subjectType"]) {
        "persona" => FollowSubjectKind.persona,
        "homepage" => FollowSubjectKind.homepage,
        "circle" => FollowSubjectKind.circle,
        "location" => FollowSubjectKind.location,
        _ => throw FormatException(
          '$path.subjectType' + ' has an invalid enum value',
        ),
      },
      visitedAt: _generatedRequestTimestamp(
        map["visitedAt"],
        '$path.visitedAt',
      ),
      clientRequestId: map["clientRequestId"] == null
          ? null
          : _generatedRequestString(
              map["clientRequestId"],
              '$path.clientRequestId',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectId": this.subjectId,
    "subjectType": this.subjectType.wireName,
    "visitedAt": this.visitedAt.toUtc().toIso8601String(),
    if (this.clientRequestId?.isNotEmpty == true)
      "clientRequestId": this.clientRequestId!,
  };
}

final class OtpDeliveryReadinessQuery {
  const OtpDeliveryReadinessQuery();
}

final class PersonaRelationshipListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  PersonaRelationshipListQuery({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       query = query,
       cursor = cursor,
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String personaId;
  final String? query;
  final String? cursor;
  final int limit;

  factory PersonaRelationshipListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "PersonaRelationshipListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "query",
      "cursor",
      "limit",
    }, path);
    return PersonaRelationshipListQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      query: map["query"] == null
          ? null
          : _generatedRequestString(map["query"], '$path.query'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    if (this.query?.isNotEmpty == true) "query": this.query!,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ProfileUpdateProposalListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ProfileUpdateProposalListQuery({
    required String personaId,
    String? cursor,
    int limit = 20,
  }) : personaId = personaId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String personaId;
  final String? cursor;
  final int limit;

  factory ProfileUpdateProposalListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ProfileUpdateProposalListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "cursor",
      "limit",
    }, path);
    return ProfileUpdateProposalListQuery(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ProfileUpdateProposalQuery {
  ProfileUpdateProposalQuery({required String proposalId})
    : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
  }

  final String proposalId;

  factory ProfileUpdateProposalQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ProfileUpdateProposalQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return ProfileUpdateProposalQuery(
      proposalId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.proposalId};
}

final class RefreshTokenCommand {
  RefreshTokenCommand({required String refreshToken})
    : refreshToken = refreshToken.trim() {
    if (this.refreshToken.isEmpty) {
      throw ArgumentError.value(
        this.refreshToken,
        "refreshToken",
        'must not be blank',
      );
    }
  }

  final String refreshToken;

  factory RefreshTokenCommand.fromWire(
    Map<String, Object?> map, [
    String path = "RefreshTokenCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "refreshToken",
    }, path);
    return RefreshTokenCommand(
      refreshToken: _generatedRequestString(
        map["refreshToken"],
        '$path.refreshToken',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "refreshToken": this.refreshToken,
  };
}

final class RejectProfileUpdateProposalCommand {
  RejectProfileUpdateProposalCommand({required String proposalId})
    : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
  }

  final String proposalId;

  factory RejectProfileUpdateProposalCommand.fromWire(
    Map<String, Object?> map, [
    String path = "RejectProfileUpdateProposalCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return RejectProfileUpdateProposalCommand(
      proposalId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.proposalId};
}

final class ReplyGreetingCommand {
  ReplyGreetingCommand({required String requestId})
    : requestId = requestId.trim() {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(
        this.requestId,
        "requestId",
        'must not be blank',
      );
    }
  }

  final String requestId;

  factory ReplyGreetingCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ReplyGreetingCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "requestId",
    }, path);
    return ReplyGreetingCommand(
      requestId: _generatedRequestString(map["requestId"], '$path.requestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class ResolveOneTapLoginHintCommand {
  ResolveOneTapLoginHintCommand({
    required String vendor,
    required String carrierToken,
    required String deviceId,
    required String platform,
    String? appVersion,
  }) : vendor = vendor.trim(),
       carrierToken = carrierToken.trim(),
       deviceId = deviceId.trim(),
       platform = platform.trim(),
       appVersion = appVersion {
    if (this.vendor.isEmpty) {
      throw ArgumentError.value(this.vendor, "vendor", 'must not be blank');
    }
    if (this.carrierToken.isEmpty) {
      throw ArgumentError.value(
        this.carrierToken,
        "carrierToken",
        'must not be blank',
      );
    }
    if (this.deviceId.isEmpty) {
      throw ArgumentError.value(this.deviceId, "deviceId", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
  }

  final String vendor;
  final String carrierToken;
  final String deviceId;
  final String platform;
  final String? appVersion;

  factory ResolveOneTapLoginHintCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ResolveOneTapLoginHintCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "vendor",
      "carrierToken",
      "deviceId",
      "platform",
      "appVersion",
    }, path);
    return ResolveOneTapLoginHintCommand(
      vendor: _generatedRequestString(map["vendor"], '$path.vendor'),
      carrierToken: _generatedRequestString(
        map["carrierToken"],
        '$path.carrierToken',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "vendor": this.vendor,
    "carrierToken": this.carrierToken,
    "deviceId": this.deviceId,
    "platform": this.platform,
    if (this.appVersion != null) "appVersion": this.appVersion!,
  };
}

final class ResolveProfileQrTokenQuery {
  const ResolveProfileQrTokenQuery({required String qr, String? handle})
    : qr = qr,
      handle = handle;

  final String qr;
  final String? handle;

  factory ResolveProfileQrTokenQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ResolveProfileQrTokenQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "qr",
      "handle",
    }, path);
    return ResolveProfileQrTokenQuery(
      qr: _generatedRequestString(map["qr"], '$path.qr'),
      handle: map["handle"] == null
          ? null
          : _generatedRequestString(map["handle"], '$path.handle'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "qr": this.qr,
    if (this.handle?.isNotEmpty == true) "handle": this.handle!,
  };
}

final class RetirePersonaCommand {
  RetirePersonaCommand({required String personaId})
    : personaId = personaId.trim() {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
  }

  final String personaId;

  factory RetirePersonaCommand.fromWire(
    Map<String, Object?> map, [
    String path = "RetirePersonaCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
    }, path);
    return RetirePersonaCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
  };
}

final class RollbackProfileUpdateProposalCommand {
  RollbackProfileUpdateProposalCommand({required String proposalId})
    : proposalId = proposalId.trim() {
    if (this.proposalId.isEmpty) {
      throw ArgumentError.value(
        this.proposalId,
        "proposalId",
        'must not be blank',
      );
    }
  }

  final String proposalId;

  factory RollbackProfileUpdateProposalCommand.fromWire(
    Map<String, Object?> map, [
    String path = "RollbackProfileUpdateProposalCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"id"}, path);
    return RollbackProfileUpdateProposalCommand(
      proposalId: _generatedRequestString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"id": this.proposalId};
}

final class SearchSocialRelationsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  SearchSocialRelationsQuery({
    required String query,
    String? cursor,
    int limit = 20,
  }) : query = query,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final String query;
  final String? cursor;
  final int limit;

  factory SearchSocialRelationsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "SearchSocialRelationsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "query",
      "cursor",
      "limit",
    }, path);
    return SearchSocialRelationsQuery(
      query: _generatedRequestString(map["query"], '$path.query'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class SendGreetingCommand {
  SendGreetingCommand({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
    GreetingIntersectionRef? intersectionRef,
  }) : targetPersonaId = targetPersonaId.trim(),
       requestMessage = _normalizeGeneratedOptionalText(requestMessage),
       source = source.trim(),
       intersectionRef = intersectionRef {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
    if (this.source.isEmpty) {
      throw ArgumentError.value(this.source, "source", 'must not be blank');
    }
  }

  final String targetPersonaId;
  final String? requestMessage;
  final String source;
  final GreetingIntersectionRef? intersectionRef;

  factory SendGreetingCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SendGreetingCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetPersonaId",
      "requestMessage",
      "source",
      "intersectionRef",
    }, path);
    return SendGreetingCommand(
      targetPersonaId: _generatedRequestString(
        map["targetPersonaId"],
        '$path.targetPersonaId',
      ),
      requestMessage: map["requestMessage"] == null
          ? null
          : _generatedRequestString(
              map["requestMessage"],
              '$path.requestMessage',
            ),
      source: map.containsKey("source")
          ? _generatedRequestString(map["source"], '$path.source')
          : 'profile',
      intersectionRef: map["intersectionRef"] == null
          ? null
          : GreetingIntersectionRef.fromWire(
              _generatedRequestObject(
                map["intersectionRef"],
                '$path.intersectionRef',
              ),
              '$path.intersectionRef',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.requestMessage?.isNotEmpty == true)
      "requestMessage": this.requestMessage!,
    "source": this.source,
    if (this.intersectionRef != null)
      "intersectionRef": this.intersectionRef!.toWire(),
  };
}

final class SendOtpCommand {
  SendOtpCommand({
    required String phone,
    String? deviceId,
    required OtpClientPlatform platform,
    String? appVersion,
    String? sourceOperation,
    String? bindingTicket,
  }) : phone = phone.trim(),
       deviceId = deviceId,
       platform = platform,
       appVersion = appVersion,
       sourceOperation = sourceOperation,
       bindingTicket = bindingTicket {
    if (this.phone.isEmpty) {
      throw ArgumentError.value(this.phone, "phone", 'must not be blank');
    }
  }

  final String phone;
  final String? deviceId;
  final OtpClientPlatform platform;
  final String? appVersion;
  final String? sourceOperation;
  final String? bindingTicket;

  factory SendOtpCommand.fromWire(
    Map<String, Object?> map, [
    String path = "SendOtpCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "phone",
      "deviceId",
      "platform",
      "appVersion",
      "sourceOperation",
      "bindingTicket",
    }, path);
    return SendOtpCommand(
      phone: _generatedRequestString(map["phone"], '$path.phone'),
      deviceId: map["deviceId"] == null
          ? null
          : _generatedRequestString(map["deviceId"], '$path.deviceId'),
      platform: switch (map["platform"]) {
        "ios" => OtpClientPlatform.ios,
        "android" => OtpClientPlatform.android,
        "web" => OtpClientPlatform.web,
        "acceptance" => OtpClientPlatform.acceptance,
        _ => throw FormatException(
          '$path.platform' + ' has an invalid enum value',
        ),
      },
      appVersion: map["appVersion"] == null
          ? null
          : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      sourceOperation: map["sourceOperation"] == null
          ? null
          : _generatedRequestString(
              map["sourceOperation"],
              '$path.sourceOperation',
            ),
      bindingTicket: map["bindingTicket"] == null
          ? null
          : _generatedRequestString(
              map["bindingTicket"],
              '$path.bindingTicket',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "phone": this.phone,
    if (this.deviceId != null) "deviceId": this.deviceId!,
    "platform": this.platform.wireName,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.sourceOperation != null) "sourceOperation": this.sourceOperation!,
    if (this.bindingTicket != null) "bindingTicket": this.bindingTicket!,
  };
}

final class UnbindCredentialCommand {
  UnbindCredentialCommand({required String credentialType})
    : credentialType = credentialType.trim() {
    if (this.credentialType.isEmpty) {
      throw ArgumentError.value(
        this.credentialType,
        "credentialType",
        'must not be blank',
      );
    }
  }

  final String credentialType;

  factory UnbindCredentialCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UnbindCredentialCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "credentialType",
    }, path);
    return UnbindCredentialCommand(
      credentialType: _generatedRequestString(
        map["credentialType"],
        '$path.credentialType',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "credentialType": this.credentialType,
  };
}

final class UnblockUserCommand {
  UnblockUserCommand({required String targetPersonaId})
    : targetPersonaId = targetPersonaId.trim() {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
  }

  final String targetPersonaId;

  factory UnblockUserCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UnblockUserCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetPersonaId",
    }, path);
    return UnblockUserCommand(
      targetPersonaId: _generatedRequestString(
        map["targetPersonaId"],
        '$path.targetPersonaId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
  };
}

final class UnfollowSubjectCommand {
  UnfollowSubjectCommand({
    required SubjectFollowTargetKind subjectType,
    required String subjectId,
  }) : subjectType = subjectType,
       subjectId = subjectId.trim() {
    if (this.subjectId.isEmpty) {
      throw ArgumentError.value(
        this.subjectId,
        "subjectId",
        'must not be blank',
      );
    }
  }

  final SubjectFollowTargetKind subjectType;
  final String subjectId;

  factory UnfollowSubjectCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UnfollowSubjectCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "subjectType",
      "subjectId",
    }, path);
    return UnfollowSubjectCommand(
      subjectType: switch (map["subjectType"]) {
        "homepage" => SubjectFollowTargetKind.homepage,
        "circle" => SubjectFollowTargetKind.circle,
        "location" => SubjectFollowTargetKind.location,
        _ => throw FormatException(
          '$path.subjectType' + ' has an invalid enum value',
        ),
      },
      subjectId: _generatedRequestString(map["subjectId"], '$path.subjectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subjectType": this.subjectType.wireName,
    "subjectId": this.subjectId,
  };
}

final class UnfollowUserCommand {
  UnfollowUserCommand({
    required String targetPersonaId,
    String? clientRequestId,
  }) : targetPersonaId = targetPersonaId.trim(),
       clientRequestId = clientRequestId {
    if (this.targetPersonaId.isEmpty) {
      throw ArgumentError.value(
        this.targetPersonaId,
        "targetPersonaId",
        'must not be blank',
      );
    }
  }

  final String targetPersonaId;
  final String? clientRequestId;

  factory UnfollowUserCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UnfollowUserCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "targetPersonaId",
      "clientRequestId",
    }, path);
    return UnfollowUserCommand(
      targetPersonaId: _generatedRequestString(
        map["targetPersonaId"],
        '$path.targetPersonaId',
      ),
      clientRequestId: map["clientRequestId"] == null
          ? null
          : _generatedRequestString(
              map["clientRequestId"],
              '$path.clientRequestId',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetPersonaId": this.targetPersonaId,
    if (this.clientRequestId?.isNotEmpty == true)
      "clientRequestId": this.clientRequestId!,
  };
}

final class UpdateAppearanceSettingsCommand {
  const UpdateAppearanceSettingsCommand({
    required ThemeModeSetting themeMode,
    required FontSizePreset fontSizePreset,
    required AppearanceApplyScope applyScope,
  }) : themeMode = themeMode,
       fontSizePreset = fontSizePreset,
       applyScope = applyScope;

  final ThemeModeSetting themeMode;
  final FontSizePreset fontSizePreset;
  final AppearanceApplyScope applyScope;

  factory UpdateAppearanceSettingsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateAppearanceSettingsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "themeMode",
      "fontSizePreset",
      "applyScope",
    }, path);
    return UpdateAppearanceSettingsCommand(
      themeMode: switch (map["themeMode"]) {
        "system" => ThemeModeSetting.system,
        "light" => ThemeModeSetting.light,
        "dark" => ThemeModeSetting.dark,
        _ => throw FormatException(
          '$path.themeMode' + ' has an invalid enum value',
        ),
      },
      fontSizePreset: switch (map["fontSizePreset"]) {
        "xs" => FontSizePreset.xs,
        "sm" => FontSizePreset.sm,
        "md" => FontSizePreset.md,
        "lg" => FontSizePreset.lg,
        "xl" => FontSizePreset.xl,
        _ => throw FormatException(
          '$path.fontSizePreset' + ' has an invalid enum value',
        ),
      },
      applyScope: switch (map["applyScope"]) {
        "all_accounts" => AppearanceApplyScope.allAccounts,
        "current_persona" => AppearanceApplyScope.currentPersona,
        "inherit_owner_default" => AppearanceApplyScope.inheritOwnerDefault,
        _ => throw FormatException(
          '$path.applyScope' + ' has an invalid enum value',
        ),
      },
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "themeMode": this.themeMode.wireName,
    "fontSizePreset": this.fontSizePreset.wireName,
    "applyScope": this.applyScope.wireName,
  };
}

final class UpdateCallSettingsCommand {
  const UpdateCallSettingsCommand({
    String? defaultIncomingCallRingtoneId,
    bool? allowCallerRingtoneOverride,
    bool? enableCallVibration,
    bool? enableGroupCallRing,
  }) : defaultIncomingCallRingtoneId = defaultIncomingCallRingtoneId,
       allowCallerRingtoneOverride = allowCallerRingtoneOverride,
       enableCallVibration = enableCallVibration,
       enableGroupCallRing = enableGroupCallRing;

  final String? defaultIncomingCallRingtoneId;
  final bool? allowCallerRingtoneOverride;
  final bool? enableCallVibration;
  final bool? enableGroupCallRing;

  factory UpdateCallSettingsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateCallSettingsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "defaultIncomingCallRingtoneId",
      "allowCallerRingtoneOverride",
      "enableCallVibration",
      "enableGroupCallRing",
    }, path);
    return UpdateCallSettingsCommand(
      defaultIncomingCallRingtoneId:
          map["defaultIncomingCallRingtoneId"] == null
          ? null
          : _generatedRequestString(
              map["defaultIncomingCallRingtoneId"],
              '$path.defaultIncomingCallRingtoneId',
            ),
      allowCallerRingtoneOverride: map["allowCallerRingtoneOverride"] == null
          ? null
          : _generatedRequestBool(
              map["allowCallerRingtoneOverride"],
              '$path.allowCallerRingtoneOverride',
            ),
      enableCallVibration: map["enableCallVibration"] == null
          ? null
          : _generatedRequestBool(
              map["enableCallVibration"],
              '$path.enableCallVibration',
            ),
      enableGroupCallRing: map["enableGroupCallRing"] == null
          ? null
          : _generatedRequestBool(
              map["enableGroupCallRing"],
              '$path.enableGroupCallRing',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.defaultIncomingCallRingtoneId != null)
      "defaultIncomingCallRingtoneId": this.defaultIncomingCallRingtoneId!,
    if (this.allowCallerRingtoneOverride != null)
      "allowCallerRingtoneOverride": this.allowCallerRingtoneOverride!,
    if (this.enableCallVibration != null)
      "enableCallVibration": this.enableCallVibration!,
    if (this.enableGroupCallRing != null)
      "enableGroupCallRing": this.enableGroupCallRing!,
  };
}

final class UpdateNotificationSettingsCommand {
  const UpdateNotificationSettingsCommand({
    bool? enablePush,
    bool? enableMarketing,
    String? quietHoursStart,
    String? quietHoursEnd,
  }) : enablePush = enablePush,
       enableMarketing = enableMarketing,
       quietHoursStart = quietHoursStart,
       quietHoursEnd = quietHoursEnd;

  final bool? enablePush;
  final bool? enableMarketing;
  final String? quietHoursStart;
  final String? quietHoursEnd;

  factory UpdateNotificationSettingsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateNotificationSettingsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "enablePush",
      "enableMarketing",
      "quietHoursStart",
      "quietHoursEnd",
    }, path);
    return UpdateNotificationSettingsCommand(
      enablePush: map["enablePush"] == null
          ? null
          : _generatedRequestBool(map["enablePush"], '$path.enablePush'),
      enableMarketing: map["enableMarketing"] == null
          ? null
          : _generatedRequestBool(
              map["enableMarketing"],
              '$path.enableMarketing',
            ),
      quietHoursStart: map["quietHoursStart"] == null
          ? null
          : _generatedRequestString(
              map["quietHoursStart"],
              '$path.quietHoursStart',
            ),
      quietHoursEnd: map["quietHoursEnd"] == null
          ? null
          : _generatedRequestString(
              map["quietHoursEnd"],
              '$path.quietHoursEnd',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.enablePush != null) "enablePush": this.enablePush!,
    if (this.enableMarketing != null) "enableMarketing": this.enableMarketing!,
    if (this.quietHoursStart != null) "quietHoursStart": this.quietHoursStart!,
    if (this.quietHoursEnd != null) "quietHoursEnd": this.quietHoursEnd!,
  };
}

final class UpdatePersonaCommand {
  UpdatePersonaCommand({
    required String personaId,
    String? displayName,
    String? avatarUrl,
    String? backgroundUrl,
    String? isolationLevel,
    String? purposeHint,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : personaId = personaId.trim(),
       displayName = displayName,
       avatarUrl = avatarUrl,
       backgroundUrl = backgroundUrl,
       isolationLevel = isolationLevel,
       purposeHint = purposeHint,
       applyScope = applyScope,
       syncTargetIds = syncTargetIds == null
           ? null
           : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {
    if (this.personaId.isEmpty) {
      throw ArgumentError.value(
        this.personaId,
        "personaId",
        'must not be blank',
      );
    }
  }

  final String personaId;
  final String? displayName;
  final String? avatarUrl;
  final String? backgroundUrl;
  final String? isolationLevel;
  final String? purposeHint;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  factory UpdatePersonaCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdatePersonaCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "personaId",
      "displayName",
      "avatarUrl",
      "backgroundUrl",
      "isolationLevel",
      "purposeHint",
      "applyScope",
      "syncTargetIds",
      "fieldsMask",
    }, path);
    return UpdatePersonaCommand(
      personaId: _generatedRequestString(map["personaId"], '$path.personaId'),
      displayName: map["displayName"] == null
          ? null
          : _generatedRequestString(map["displayName"], '$path.displayName'),
      avatarUrl: map["avatarUrl"] == null
          ? null
          : _generatedRequestString(map["avatarUrl"], '$path.avatarUrl'),
      backgroundUrl: map["backgroundUrl"] == null
          ? null
          : _generatedRequestString(
              map["backgroundUrl"],
              '$path.backgroundUrl',
            ),
      isolationLevel: map["isolationLevel"] == null
          ? null
          : _generatedRequestString(
              map["isolationLevel"],
              '$path.isolationLevel',
            ),
      purposeHint: map["purposeHint"] == null
          ? null
          : _generatedRequestString(map["purposeHint"], '$path.purposeHint'),
      applyScope: map["applyScope"] == null
          ? null
          : _generatedRequestString(map["applyScope"], '$path.applyScope'),
      syncTargetIds: map["syncTargetIds"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["syncTargetIds"],
                '$path.syncTargetIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.syncTargetIds' + '[${entry.key}]',
                ),
              ),
            ),
      fieldsMask: map["fieldsMask"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["fieldsMask"],
                '$path.fieldsMask',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.fieldsMask' + '[${entry.key}]',
                ),
              ),
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "personaId": this.personaId,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.backgroundUrl != null) "backgroundUrl": this.backgroundUrl!,
    if (this.isolationLevel != null) "isolationLevel": this.isolationLevel!,
    if (this.purposeHint != null) "purposeHint": this.purposeHint!,
    if (this.applyScope != null) "applyScope": this.applyScope!,
    if (this.syncTargetIds != null)
      "syncTargetIds": this.syncTargetIds!
          .map((value) => value)
          .toList(growable: false),
    if (this.fieldsMask != null)
      "fieldsMask": this.fieldsMask!
          .map((value) => value)
          .toList(growable: false),
  };
}

final class UpdatePrivacySettingsCommand {
  UpdatePrivacySettingsCommand({
    bool? allowStrangerMsg,
    ProfileVisibility? profileVisibility,
    List<String>? blockedKeywords,
    bool? assistantEnabled,
  }) : allowStrangerMsg = allowStrangerMsg,
       profileVisibility = profileVisibility,
       blockedKeywords = blockedKeywords == null
           ? null
           : _normalizeGeneratedTextList(blockedKeywords, deduplicate: true),
       assistantEnabled = assistantEnabled {}

  final bool? allowStrangerMsg;
  final ProfileVisibility? profileVisibility;
  final List<String>? blockedKeywords;
  final bool? assistantEnabled;

  factory UpdatePrivacySettingsCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdatePrivacySettingsCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "allowStrangerMsg",
      "profileVisibility",
      "blockedKeywords",
      "assistantEnabled",
    }, path);
    return UpdatePrivacySettingsCommand(
      allowStrangerMsg: map["allowStrangerMsg"] == null
          ? null
          : _generatedRequestBool(
              map["allowStrangerMsg"],
              '$path.allowStrangerMsg',
            ),
      profileVisibility: map["profileVisibility"] == null
          ? null
          : switch (map["profileVisibility"]) {
              "public" => ProfileVisibility.public,
              "friends" => ProfileVisibility.friends,
              "private" => ProfileVisibility.privateProfile,
              _ => throw FormatException(
                '$path.profileVisibility' + ' has an invalid enum value',
              ),
            },
      blockedKeywords: map["blockedKeywords"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["blockedKeywords"],
                '$path.blockedKeywords',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.blockedKeywords' + '[${entry.key}]',
                ),
              ),
            ),
      assistantEnabled: map["assistantEnabled"] == null
          ? null
          : _generatedRequestBool(
              map["assistantEnabled"],
              '$path.assistantEnabled',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.allowStrangerMsg != null)
      "allowStrangerMsg": this.allowStrangerMsg!,
    if (this.profileVisibility != null)
      "profileVisibility": this.profileVisibility!.wireName,
    if (this.blockedKeywords != null)
      "blockedKeywords": this.blockedKeywords!
          .map((value) => value)
          .toList(growable: false),
    if (this.assistantEnabled != null)
      "assistantEnabled": this.assistantEnabled!,
  };
}

final class UpdateUserProfileCommand {
  UpdateUserProfileCommand({
    String? nickname,
    String? displayName,
    String? avatarAssetId,
    String? avatarUrl,
    String? backgroundAssetId,
    String? backgroundUrl,
    String? bio,
    String? gender,
    String? birthDate,
    String? regionTagRef,
    String? occupationTagRef,
    List<String>? interestTagRefs,
    String? expectedTaxonomyReleaseId,
    List<String>? identityTags,
    String? profileVisibility,
    String? applyScope,
    List<String>? syncTargetIds,
    List<String>? fieldsMask,
  }) : nickname = nickname,
       displayName = displayName,
       avatarAssetId = avatarAssetId,
       avatarUrl = avatarUrl,
       backgroundAssetId = backgroundAssetId,
       backgroundUrl = backgroundUrl,
       bio = bio,
       gender = gender,
       birthDate = birthDate,
       regionTagRef = regionTagRef,
       occupationTagRef = occupationTagRef,
       interestTagRefs = interestTagRefs == null
           ? null
           : List.unmodifiable(interestTagRefs),
       expectedTaxonomyReleaseId = _normalizeGeneratedOptionalText(
         expectedTaxonomyReleaseId,
       ),
       identityTags = identityTags == null
           ? null
           : List.unmodifiable(identityTags),
       profileVisibility = profileVisibility,
       applyScope = applyScope,
       syncTargetIds = syncTargetIds == null
           ? null
           : List.unmodifiable(syncTargetIds),
       fieldsMask = fieldsMask == null ? null : List.unmodifiable(fieldsMask) {}

  final String? nickname;
  final String? displayName;
  final String? avatarAssetId;
  final String? avatarUrl;
  final String? backgroundAssetId;
  final String? backgroundUrl;
  final String? bio;
  final String? gender;
  final String? birthDate;
  final String? regionTagRef;
  final String? occupationTagRef;
  final List<String>? interestTagRefs;
  final String? expectedTaxonomyReleaseId;
  final List<String>? identityTags;
  final String? profileVisibility;
  final String? applyScope;
  final List<String>? syncTargetIds;
  final List<String>? fieldsMask;

  factory UpdateUserProfileCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateUserProfileCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "nickname",
      "displayName",
      "avatarAssetId",
      "avatarUrl",
      "backgroundAssetId",
      "backgroundUrl",
      "bio",
      "gender",
      "birthDate",
      "regionTagRef",
      "occupationTagRef",
      "interestTagRefs",
      "expectedTaxonomyReleaseId",
      "identityTags",
      "profileVisibility",
      "applyScope",
      "syncTargetIds",
      "fieldsMask",
    }, path);
    return UpdateUserProfileCommand(
      nickname: map["nickname"] == null
          ? null
          : _generatedRequestString(map["nickname"], '$path.nickname'),
      displayName: map["displayName"] == null
          ? null
          : _generatedRequestString(map["displayName"], '$path.displayName'),
      avatarAssetId: map["avatarAssetId"] == null
          ? null
          : _generatedRequestString(
              map["avatarAssetId"],
              '$path.avatarAssetId',
            ),
      avatarUrl: map["avatarUrl"] == null
          ? null
          : _generatedRequestString(map["avatarUrl"], '$path.avatarUrl'),
      backgroundAssetId: map["backgroundAssetId"] == null
          ? null
          : _generatedRequestString(
              map["backgroundAssetId"],
              '$path.backgroundAssetId',
            ),
      backgroundUrl: map["backgroundUrl"] == null
          ? null
          : _generatedRequestString(
              map["backgroundUrl"],
              '$path.backgroundUrl',
            ),
      bio: map["bio"] == null
          ? null
          : _generatedRequestString(map["bio"], '$path.bio'),
      gender: map["gender"] == null
          ? null
          : _generatedRequestString(map["gender"], '$path.gender'),
      birthDate: map["birthDate"] == null
          ? null
          : _generatedRequestString(map["birthDate"], '$path.birthDate'),
      regionTagRef: map["regionTagRef"] == null
          ? null
          : _generatedRequestString(map["regionTagRef"], '$path.regionTagRef'),
      occupationTagRef: map["occupationTagRef"] == null
          ? null
          : _generatedRequestString(
              map["occupationTagRef"],
              '$path.occupationTagRef',
            ),
      interestTagRefs: map["interestTagRefs"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["interestTagRefs"],
                '$path.interestTagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.interestTagRefs' + '[${entry.key}]',
                ),
              ),
            ),
      expectedTaxonomyReleaseId: map["expectedTaxonomyReleaseId"] == null
          ? null
          : _generatedRequestString(
              map["expectedTaxonomyReleaseId"],
              '$path.expectedTaxonomyReleaseId',
            ),
      identityTags: map["identityTags"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["identityTags"],
                '$path.identityTags',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.identityTags' + '[${entry.key}]',
                ),
              ),
            ),
      profileVisibility: map["profileVisibility"] == null
          ? null
          : _generatedRequestString(
              map["profileVisibility"],
              '$path.profileVisibility',
            ),
      applyScope: map["applyScope"] == null
          ? null
          : _generatedRequestString(map["applyScope"], '$path.applyScope'),
      syncTargetIds: map["syncTargetIds"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["syncTargetIds"],
                '$path.syncTargetIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.syncTargetIds' + '[${entry.key}]',
                ),
              ),
            ),
      fieldsMask: map["fieldsMask"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["fieldsMask"],
                '$path.fieldsMask',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.fieldsMask' + '[${entry.key}]',
                ),
              ),
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.nickname != null) "nickname": this.nickname!,
    if (this.displayName != null) "displayName": this.displayName!,
    if (this.avatarAssetId != null) "avatarAssetId": this.avatarAssetId!,
    if (this.avatarUrl != null) "avatarUrl": this.avatarUrl!,
    if (this.backgroundAssetId != null)
      "backgroundAssetId": this.backgroundAssetId!,
    if (this.backgroundUrl != null) "backgroundUrl": this.backgroundUrl!,
    if (this.bio != null) "bio": this.bio!,
    if (this.gender != null) "gender": this.gender!,
    if (this.birthDate != null) "birthDate": this.birthDate!,
    if (this.regionTagRef != null) "regionTagRef": this.regionTagRef!,
    if (this.occupationTagRef != null)
      "occupationTagRef": this.occupationTagRef!,
    if (this.interestTagRefs != null)
      "interestTagRefs": this.interestTagRefs!
          .map((value) => value)
          .toList(growable: false),
    if (this.expectedTaxonomyReleaseId != null)
      "expectedTaxonomyReleaseId": this.expectedTaxonomyReleaseId!,
    if (this.identityTags != null)
      "identityTags": this.identityTags!
          .map((value) => value)
          .toList(growable: false),
    if (this.profileVisibility != null)
      "profileVisibility": this.profileVisibility!,
    if (this.applyScope != null) "applyScope": this.applyScope!,
    if (this.syncTargetIds != null)
      "syncTargetIds": this.syncTargetIds!
          .map((value) => value)
          .toList(growable: false),
    if (this.fieldsMask != null)
      "fieldsMask": this.fieldsMask!
          .map((value) => value)
          .toList(growable: false),
  };
}

final class UserSettingsQuery {
  const UserSettingsQuery();
}

final class UserSyncPullRequestWire {
  const UserSyncPullRequestWire({int? afterSeq, int? limit})
    : afterSeq = afterSeq,
      limit = limit;

  final int? afterSeq;
  final int? limit;

  factory UserSyncPullRequestWire.fromWire(
    Map<String, Object?> map, [
    String path = "UserSyncPullRequestWire",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "afterSeq",
      "limit",
    }, path);
    return UserSyncPullRequestWire(
      afterSeq: map["afterSeq"] == null
          ? null
          : _generatedRequestInt(map["afterSeq"], '$path.afterSeq'),
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.afterSeq != null) "afterSeq": this.afterSeq!,
    if (this.limit != null) "limit": this.limit!,
  };
}

CloudOperationRequestPayload
encodeUserAccountSessionIssueWhitelistedResearchSessionGeneratedRequest(
  IssueWhitelistedResearchSessionCommand request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginAnonymousGeneratedRequest(
  LoginAnonymousCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "installId": request.installId,
      "deviceFingerprintHash": request.deviceFingerprintHash,
      "platform": request.platform,
      "appVersion": request.appVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginOneTapGeneratedRequest(
  LoginOneTapCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginWithAlipayGeneratedRequest(
  LoginWithAlipayCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "alipayAuthCode": request.alipayAuthCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginWithPhoneGeneratedRequest(
  LoginWithPhoneCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      "otpCode": request.otpCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      "appVersion": request.appVersion,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginWithQqGeneratedRequest(
  LoginWithQqCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "qqAuthCode": request.qqAuthCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionLoginWithWechatGeneratedRequest(
  LoginWithWechatCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "wechatCode": request.wechatCode,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload encodeUserAccountSessionLogoutGeneratedRequest(
  LogoutCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.refreshToken != null) "refreshToken": request.refreshToken!,
      if (request.deviceId != null) "deviceId": request.deviceId!,
    },
  );
}

CloudOperationRequestPayload
encodeUserAccountSessionRefreshTokenGeneratedRequest(
  RefreshTokenCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{"refreshToken": request.refreshToken},
  );
}

CloudOperationRequestPayload
encodeUserAuthenticationChallengeCreateAlipayAuthorizationRequestGeneratedRequest(
  CreateAlipayAuthorizationRequestCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.platform != null) "platform": request.platform!,
      if (request.appVersion != null) "appVersion": request.appVersion!,
    },
  );
}

CloudOperationRequestPayload
encodeUserAuthenticationChallengeGetOtpDeliveryReadinessGeneratedRequest(
  OtpDeliveryReadinessQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserAuthenticationChallengeResolveOneTapLoginHintGeneratedRequest(
  ResolveOneTapLoginHintCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.appVersion != null) "appVersion": request.appVersion!,
    },
  );
}

CloudOperationRequestPayload
encodeUserAuthenticationChallengeSendOtpGeneratedRequest(
  SendOtpCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      if (request.deviceId != null) "deviceId": request.deviceId!,
      "platform": request.platform.wireName,
      if (request.appVersion != null) "appVersion": request.appVersion!,
      if (request.sourceOperation != null)
        "sourceOperation": request.sourceOperation!,
      if (request.bindingTicket != null)
        "bindingTicket": request.bindingTicket!,
    },
  );
}

CloudOperationRequestPayload
encodeUserContactDiscoveryRecordDismissContactDiscoveryGeneratedRequest(
  DismissContactDiscoveryCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.discoveryId},
  );
}

CloudOperationRequestPayload
encodeUserContactDiscoveryRecordGetLatestContactDiscoveryGeneratedRequest(
  GetLatestContactDiscoveryQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserContactDiscoveryRecordInitiateContactDiscoveryGeneratedRequest(
  InitiateContactDiscoveryCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "hashedPhones": request.hashedPhones
          .map((value) => value)
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeUserCredentialBindingBindCarrierPhoneCredentialGeneratedRequest(
  BindCarrierPhoneCredentialCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "vendor": request.vendor,
      "carrierToken": request.carrierToken,
      "deviceId": request.deviceId,
      "platform": request.platform,
      if (request.displayLabel != null) "displayLabel": request.displayLabel!,
    },
  );
}

CloudOperationRequestPayload
encodeUserCredentialBindingBindPhoneCredentialGeneratedRequest(
  BindPhoneCredentialCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "phone": request.phone,
      "otpCode": request.otpCode,
      if (request.displayLabel != null) "displayLabel": request.displayLabel!,
    },
  );
}

CloudOperationRequestPayload
encodeUserCredentialBindingCompleteFederatedPhoneBindingGeneratedRequest(
  CompleteFederatedPhoneBindingCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "bindingTicket": request.bindingTicket,
      "phone": request.phone,
      "otpCode": request.otpCode,
      "challengeId": request.challengeId,
      "deviceId": request.deviceId,
      "platform": request.platform,
      "appVersion": request.appVersion,
      "agreementVersion": request.agreementVersion,
      "privacyVersion": request.privacyVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserCredentialBindingListCredentialsGeneratedRequest(
  ListCredentialsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserCredentialBindingUnbindCredentialGeneratedRequest(
  UnbindCredentialCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"credentialType": request.credentialType},
  );
}

CloudOperationRequestPayload
encodeUserDeviceRegistrationRemoveDevicePushEndpointGeneratedRequest(
  DevicePushEndpointRemoveCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "deviceId": request.deviceId,
      "endpointKind": (request.endpointKind.wireName).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserDeviceRegistrationUpsertDevicePushEndpointGeneratedRequest(
  DevicePushEndpointUpsertCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "deviceId": request.deviceId,
      "endpointKind": (request.endpointKind.wireName).toString(),
    },
    body: <String, Object?>{
      "token": request.token,
      "appVersion": request.appVersion,
    },
  );
}

CloudOperationRequestPayload
encodeUserFollowedSubjectVisitStateMarkFollowedSubjectVisitedGeneratedRequest(
  MarkFollowedSubjectVisitedCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (request.subjectType.wireName).toString(),
      "subjectId": request.subjectId,
    },
    body: <String, Object?>{
      "visitedAt": request.visitedAt.toUtc().toIso8601String(),
      if (request.clientRequestId?.isNotEmpty == true)
        "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload
encodeUserFollowingSubjectListFollowingSubjectsGeneratedRequest(
  ListFollowingSubjectsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.subjectType != null)
        "subjectType": (request.subjectType!.wireName).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestCancelGreetingRequestGeneratedRequest(
  CancelGreetingCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"requestId": request.requestId},
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestIgnoreGreetingRequestGeneratedRequest(
  IgnoreGreetingCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"requestId": request.requestId},
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestListGreetingInboxGeneratedRequest(
  ListGreetingRequestsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.status.isNotEmpty) "status": request.status,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestListGreetingOutboxGeneratedRequest(
  ListGreetingRequestsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.status.isNotEmpty) "status": request.status,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestReplyGreetingRequestGeneratedRequest(
  ReplyGreetingCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"requestId": request.requestId},
  );
}

CloudOperationRequestPayload
encodeUserGreetingRequestSendGreetingRequestGeneratedRequest(
  SendGreetingCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "targetPersonaId": request.targetPersonaId,
      if (request.requestMessage?.isNotEmpty == true)
        "requestMessage": request.requestMessage!,
      "source": request.source,
      if (request.intersectionRef != null)
        "intersectionRef": request.intersectionRef!.toWire(),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaActivatePersonaGeneratedRequest(
  ActivatePersonaCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
  );
}

CloudOperationRequestPayload
encodeUserPersonaApplyPersonaProfileSyncGeneratedRequest(
  ApplyPersonaProfileSyncCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    body: <String, Object?>{
      "applyScope": request.applyScope,
      if (request.syncTargetIds != null)
        "syncTargetIds": request.syncTargetIds!
            .map((value) => value)
            .toList(growable: false),
      if (request.fieldsMask != null)
        "fieldsMask": request.fieldsMask!
            .map((value) => value)
            .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaCreatePersonaGeneratedRequest(
  CreatePersonaCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "displayName": request.displayName,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.isolationLevel != null)
        "isolationLevel": request.isolationLevel!,
      if (request.purposeHint != null) "purposeHint": request.purposeHint!,
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaRetirePersonaGeneratedRequest(
  RetirePersonaCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
  );
}

CloudOperationRequestPayload encodeUserPersonaUpdatePersonaGeneratedRequest(
  UpdatePersonaCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    body: <String, Object?>{
      if (request.displayName != null) "displayName": request.displayName!,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.backgroundUrl != null)
        "backgroundUrl": request.backgroundUrl!,
      if (request.isolationLevel != null)
        "isolationLevel": request.isolationLevel!,
      if (request.purposeHint != null) "purposeHint": request.purposeHint!,
      if (request.applyScope != null) "applyScope": request.applyScope!,
      if (request.syncTargetIds != null)
        "syncTargetIds": request.syncTargetIds!
            .map((value) => value)
            .toList(growable: false),
      if (request.fieldsMask != null)
        "fieldsMask": request.fieldsMask!
            .map((value) => value)
            .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeUserPersonaUpdateUserProfileGeneratedRequest(
  UpdateUserProfileCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.nickname != null) "nickname": request.nickname!,
      if (request.displayName != null) "displayName": request.displayName!,
      if (request.avatarAssetId != null)
        "avatarAssetId": request.avatarAssetId!,
      if (request.avatarUrl != null) "avatarUrl": request.avatarUrl!,
      if (request.backgroundAssetId != null)
        "backgroundAssetId": request.backgroundAssetId!,
      if (request.backgroundUrl != null)
        "backgroundUrl": request.backgroundUrl!,
      if (request.bio != null) "bio": request.bio!,
      if (request.gender != null) "gender": request.gender!,
      if (request.birthDate != null) "birthDate": request.birthDate!,
      if (request.regionTagRef != null) "regionTagRef": request.regionTagRef!,
      if (request.occupationTagRef != null)
        "occupationTagRef": request.occupationTagRef!,
      if (request.interestTagRefs != null)
        "interestTagRefs": request.interestTagRefs!
            .map((value) => value)
            .toList(growable: false),
      if (request.expectedTaxonomyReleaseId != null)
        "expectedTaxonomyReleaseId": request.expectedTaxonomyReleaseId!,
      if (request.identityTags != null)
        "identityTags": request.identityTags!
            .map((value) => value)
            .toList(growable: false),
      if (request.profileVisibility != null)
        "profileVisibility": request.profileVisibility!,
      if (request.applyScope != null) "applyScope": request.applyScope!,
      if (request.syncTargetIds != null)
        "syncTargetIds": request.syncTargetIds!
            .map((value) => value)
            .toList(growable: false),
      if (request.fieldsMask != null)
        "fieldsMask": request.fieldsMask!
            .map((value) => value)
            .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipBlockUserGeneratedRequest(
  BlockUserCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipFollowUserGeneratedRequest(
  FollowUserCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
    body: <String, Object?>{
      if (request.source?.isNotEmpty == true) "source": request.source!,
      if (request.clientRequestId?.isNotEmpty == true)
        "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipGetRelationshipCapabilityGeneratedRequest(
  GetRelationshipCapabilityQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.targetPersonaId},
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipListBlockedUsersGeneratedRequest(
  ListBlockedUsersQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipListFollowersGeneratedRequest(
  PersonaRelationshipListQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      if (request.query?.isNotEmpty == true) "query": request.query!,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipListFollowingGeneratedRequest(
  PersonaRelationshipListQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      if (request.query?.isNotEmpty == true) "query": request.query!,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipUnblockUserGeneratedRequest(
  UnblockUserCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
  );
}

CloudOperationRequestPayload
encodeUserPersonaRelationshipUnfollowUserGeneratedRequest(
  UnfollowUserCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "targetPersonaId": request.targetPersonaId,
    },
    body: <String, Object?>{
      if (request.clientRequestId?.isNotEmpty == true)
        "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalApplyProposalGeneratedRequest(
  ApplyProfileUpdateProposalCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.proposalId},
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalConfirmProposalGeneratedRequest(
  ConfirmProfileUpdateProposalCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.proposalId},
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalCreateProfileUpdateProposalGeneratedRequest(
  CreateProfileUpdateProposalCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    body: <String, Object?>{
      "proposalId": request.proposalId,
      "source": request.source.wireName,
      if (request.displayName != null) "displayName": request.displayName!,
      if (request.bio != null) "bio": request.bio!,
      if (request.avatarMediaAssetId != null)
        "avatarMediaAssetId": request.avatarMediaAssetId!,
      if (request.backgroundMediaAssetId != null)
        "backgroundMediaAssetId": request.backgroundMediaAssetId!,
      if (request.isPrivate != null) "isPrivate": request.isPrivate!,
      if (request.isolationLevel != null)
        "isolationLevel": request.isolationLevel!,
      if (request.purposeHint != null) "purposeHint": request.purposeHint!,
      "reason": request.reason,
      "evidenceRefs": request.evidenceRefs
          .map((value) => value)
          .toList(growable: false),
      "impactScope": request.impactScope
          .map((value) => value)
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalGetProfileUpdateProposalGeneratedRequest(
  ProfileUpdateProposalQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.proposalId},
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalListProfileUpdateProposalsGeneratedRequest(
  ProfileUpdateProposalListQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalRejectProposalGeneratedRequest(
  RejectProfileUpdateProposalCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.proposalId},
  );
}

CloudOperationRequestPayload
encodeUserProfileUpdateProposalRollbackProposalGeneratedRequest(
  RollbackProfileUpdateProposalCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"id": request.proposalId},
  );
}

CloudOperationRequestPayload
encodeUserSubjectFollowFollowSubjectGeneratedRequest(
  FollowSubjectCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (request.subjectType.wireName).toString(),
      "subjectId": request.subjectId,
    },
    body: <String, Object?>{
      if (request.source != null) "source": request.source!,
    },
  );
}

CloudOperationRequestPayload
encodeUserSubjectFollowUnfollowSubjectGeneratedRequest(
  UnfollowSubjectCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "subjectType": (request.subjectType.wireName).toString(),
      "subjectId": request.subjectId,
    },
  );
}

CloudOperationRequestPayload encodeUserUserAccountCloseAccountGeneratedRequest(
  CloseAccountCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.clientRequestId != null)
        "clientRequestId": request.clientRequestId!,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserAccountGetActivePersonaContextGeneratedRequest(
  GetActivePersonaContextQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload encodeUserUserAccountGetMeProfileGeneratedRequest(
  GetMeProfileQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserAccountGetPersonaLifecycleGuardGeneratedRequest(
  GetPersonaLifecycleGuardQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
  );
}

CloudOperationRequestPayload
encodeUserUserAccountGetPersonaManagementSummaryGeneratedRequest(
  GetPersonaManagementSummaryQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserAccountGetPersonaProfileGeneratedRequest(
  GetPersonaProfileQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
  );
}

CloudOperationRequestPayload
encodeUserUserAccountGetProfileEditSnapshotGeneratedRequest(
  GetProfileEditSnapshotQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserAccountGetProfileQrCardGeneratedRequest(
  GetProfileQrCardQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserAccountGetUserHomepageBundleGeneratedRequest(
  GetUserHomepageBundleQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"personaId": request.personaId},
  );
}

CloudOperationRequestPayload encodeUserUserAccountListPersonasGeneratedRequest(
  ListPersonasQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload encodeUserUserAccountPullUserSyncGeneratedRequest(
  UserSyncPullRequestWire request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.afterSeq != null) "afterSeq": request.afterSeq!,
      if (request.limit != null) "limit": request.limit!,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserAccountResolveProfileQrTokenGeneratedRequest(
  ResolveProfileQrTokenQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "qr": request.qr,
      if (request.handle?.isNotEmpty == true) "handle": request.handle!,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserAccountSearchSocialRelationsGeneratedRequest(
  SearchSocialRelationsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "query": request.query,
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeUserUserSettingsGetAppearanceSettingsGeneratedRequest(
  UserSettingsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserSettingsGetCallSettingsGeneratedRequest(
  UserSettingsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserSettingsGetNotificationSettingsGeneratedRequest(
  UserSettingsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserSettingsGetPrivacySettingsGeneratedRequest(
  UserSettingsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeUserUserSettingsUpdateAppearanceSettingsGeneratedRequest(
  UpdateAppearanceSettingsCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "themeMode": request.themeMode.wireName,
      "fontSizePreset": request.fontSizePreset.wireName,
      "applyScope": request.applyScope.wireName,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserSettingsUpdateCallSettingsGeneratedRequest(
  UpdateCallSettingsCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.defaultIncomingCallRingtoneId != null)
        "defaultIncomingCallRingtoneId": request.defaultIncomingCallRingtoneId!,
      if (request.allowCallerRingtoneOverride != null)
        "allowCallerRingtoneOverride": request.allowCallerRingtoneOverride!,
      if (request.enableCallVibration != null)
        "enableCallVibration": request.enableCallVibration!,
      if (request.enableGroupCallRing != null)
        "enableGroupCallRing": request.enableGroupCallRing!,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserSettingsUpdateNotificationSettingsGeneratedRequest(
  UpdateNotificationSettingsCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.enablePush != null) "enablePush": request.enablePush!,
      if (request.enableMarketing != null)
        "enableMarketing": request.enableMarketing!,
      if (request.quietHoursStart != null)
        "quietHoursStart": request.quietHoursStart!,
      if (request.quietHoursEnd != null)
        "quietHoursEnd": request.quietHoursEnd!,
    },
  );
}

CloudOperationRequestPayload
encodeUserUserSettingsUpdatePrivacySettingsGeneratedRequest(
  UpdatePrivacySettingsCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.allowStrangerMsg != null)
        "allowStrangerMsg": request.allowStrangerMsg!,
      if (request.profileVisibility != null)
        "profileVisibility": request.profileVisibility!.wireName,
      if (request.blockedKeywords != null)
        "blockedKeywords": request.blockedKeywords!
            .map((value) => value)
            .toList(growable: false),
      if (request.assistantEnabled != null)
        "assistantEnabled": request.assistantEnabled!,
    },
  );
}
