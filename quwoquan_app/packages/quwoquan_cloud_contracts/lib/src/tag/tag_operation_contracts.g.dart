// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: ae0fd0a3a81ca25ad321276e82c2668626920098032d6fa00232e4637c87fa28

library;

import '../operation_request_payload.dart';

part '../generated/requests/tag/tag_operation_contracts.g.requests.g.dart';

enum TagFeedbackAction {
  click("click"),
  ignore("ignore"),
  correct("correct"),
  dislike("dislike");

  const TagFeedbackAction(this.wireName);

  final String wireName;

  static TagFeedbackAction fromWire(Object? value, String path) {
    return switch (value) {
      "click" => TagFeedbackAction.click,
      "ignore" => TagFeedbackAction.ignore,
      "correct" => TagFeedbackAction.correct,
      "dislike" => TagFeedbackAction.dislike,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TagHeatRecurrence {
  once("once"),
  annual("annual");

  const TagHeatRecurrence(this.wireName);

  final String wireName;

  static TagHeatRecurrence fromWire(Object? value, String path) {
    return switch (value) {
      "once" => TagHeatRecurrence.once,
      "annual" => TagHeatRecurrence.annual,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum TagLifecycleStatus {
  active("active"),
  trending("trending"),
  seasonal("seasonal"),
  campaign("campaign"),
  deprecated("deprecated");

  const TagLifecycleStatus(this.wireName);

  final String wireName;

  static TagLifecycleStatus fromWire(Object? value, String path) {
    return switch (value) {
      "active" => TagLifecycleStatus.active,
      "trending" => TagLifecycleStatus.trending,
      "seasonal" => TagLifecycleStatus.seasonal,
      "campaign" => TagLifecycleStatus.campaign,
      "deprecated" => TagLifecycleStatus.deprecated,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class TagChildView {
  const TagChildView({
    required this.tagRef,
    required this.label,
    this.displayLabel,
    this.labelEn,
    required this.parentTagRef,
    required this.depth,
    required this.hasChildren,
    required this.releaseId,
    required this.lifecycleStatus,
    this.heatWindow,
  });

  final String tagRef;
  final String label;
  final String? displayLabel;
  final String? labelEn;
  final String parentTagRef;
  final int depth;
  final bool hasChildren;
  final String releaseId;
  final TagLifecycleStatus lifecycleStatus;
  final TagHeatWindow? heatWindow;

  factory TagChildView.fromWire(Map<String, Object?> map, [String path = "TagChildView"]) {
    _rejectUnknownFields(map, const <String>{"tagRef", "label", "displayLabel", "labelEn", "parentTagRef", "depth", "hasChildren", "releaseId", "lifecycleStatus", "heatWindow"}, path);
    return TagChildView(
      tagRef: _requiredString(map["tagRef"], '$path.tagRef'),
      label: _requiredString(map["label"], '$path.label'),
      displayLabel: map["displayLabel"] == null ? null : _requiredString(map["displayLabel"], '$path.displayLabel'),
      labelEn: map["labelEn"] == null ? null : _requiredString(map["labelEn"], '$path.labelEn'),
      parentTagRef: _requiredString(map["parentTagRef"], '$path.parentTagRef'),
      depth: _requiredInt(map["depth"], '$path.depth'),
      hasChildren: _requiredBool(map["hasChildren"], '$path.hasChildren'),
      releaseId: _requiredString(map["releaseId"], '$path.releaseId'),
      lifecycleStatus: TagLifecycleStatus.fromWire(map["lifecycleStatus"], '$path.lifecycleStatus'),
      heatWindow: map["heatWindow"] == null ? null : TagHeatWindow.fromWire(_requiredObject(map["heatWindow"], '$path.heatWindow'), '$path.heatWindow'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tagRef": tagRef,
    "label": label,
    if (displayLabel != null) "displayLabel": displayLabel!,
    if (labelEn != null) "labelEn": labelEn!,
    "parentTagRef": parentTagRef,
    "depth": depth,
    "hasChildren": hasChildren,
    "releaseId": releaseId,
    "lifecycleStatus": lifecycleStatus.wireName,
    if (heatWindow != null) "heatWindow": heatWindow!.toWire(),
  };
}

final class TagChildrenSlice {
  const TagChildrenSlice({
    required this.items,
  });

  final List<TagChildView> items;

  factory TagChildrenSlice.fromWire(Map<String, Object?> map, [String path = "TagChildrenSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return TagChildrenSlice(
      items: List<TagChildView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => TagChildView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class TagFeedbackResultView {
  const TagFeedbackResultView({
    required this.accepted,
  });

  final bool accepted;

  factory TagFeedbackResultView.fromWire(Map<String, Object?> map, [String path = "TagFeedbackResultView"]) {
    _rejectUnknownFields(map, const <String>{"accepted"}, path);
    return TagFeedbackResultView(
      accepted: _requiredBool(map["accepted"], '$path.accepted'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accepted": accepted,
  };
}

final class TagHeatWindow {
  const TagHeatWindow({
    required this.startAt,
    required this.endAt,
    required this.recurrence,
  });

  final DateTime startAt;
  final DateTime endAt;
  final TagHeatRecurrence recurrence;

  factory TagHeatWindow.fromWire(Map<String, Object?> map, [String path = "TagHeatWindow"]) {
    _rejectUnknownFields(map, const <String>{"startAt", "endAt", "recurrence"}, path);
    return TagHeatWindow(
      startAt: _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: _requiredTimestamp(map["endAt"], '$path.endAt'),
      recurrence: TagHeatRecurrence.fromWire(map["recurrence"], '$path.recurrence'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "startAt": startAt.toUtc().toIso8601String(),
    "endAt": endAt.toUtc().toIso8601String(),
    "recurrence": recurrence.wireName,
  };
}

final class TagResolveView {
  const TagResolveView({
    required this.tagRef,
    required this.group,
    required this.label,
    this.labelEn,
    this.aliases,
    this.ancestors,
    this.axisRole,
    this.sameAsRefs,
  });

  final String tagRef;
  final String group;
  final String label;
  final String? labelEn;
  final List<String>? aliases;
  final List<String>? ancestors;
  final String? axisRole;
  final List<String>? sameAsRefs;

  factory TagResolveView.fromWire(Map<String, Object?> map, [String path = "TagResolveView"]) {
    _rejectUnknownFields(map, const <String>{"tagRef", "group", "label", "labelEn", "aliases", "ancestors", "axisRole", "sameAsRefs"}, path);
    return TagResolveView(
      tagRef: _requiredString(map["tagRef"], '$path.tagRef'),
      group: _requiredString(map["group"], '$path.group'),
      label: _requiredString(map["label"], '$path.label'),
      labelEn: map["labelEn"] == null ? null : _requiredString(map["labelEn"], '$path.labelEn'),
      aliases: map["aliases"] == null ? null : List<String>.unmodifiable(_requiredList(map["aliases"], '$path.aliases').asMap().entries.map((entry) => _requiredString(entry.value, '$path.aliases' + '[${entry.key}]'))),
      ancestors: map["ancestors"] == null ? null : List<String>.unmodifiable(_requiredList(map["ancestors"], '$path.ancestors').asMap().entries.map((entry) => _requiredString(entry.value, '$path.ancestors' + '[${entry.key}]'))),
      axisRole: map["axisRole"] == null ? null : _requiredString(map["axisRole"], '$path.axisRole'),
      sameAsRefs: map["sameAsRefs"] == null ? null : List<String>.unmodifiable(_requiredList(map["sameAsRefs"], '$path.sameAsRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sameAsRefs' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "tagRef": tagRef,
    "group": group,
    "label": label,
    if (labelEn != null) "labelEn": labelEn!,
    if (aliases != null) "aliases": aliases!.map((value) => value).toList(growable: false),
    if (ancestors != null) "ancestors": ancestors!.map((value) => value).toList(growable: false),
    if (axisRole != null) "axisRole": axisRole!,
    if (sameAsRefs != null) "sameAsRefs": sameAsRefs!.map((value) => value).toList(growable: false),
  };
}

final class TagValidationResultView {
  const TagValidationResultView({
    required this.taxonomyReleaseId,
    required this.valid,
    required this.invalid,
  });

  final String taxonomyReleaseId;
  final List<String> valid;
  final List<String> invalid;

  factory TagValidationResultView.fromWire(Map<String, Object?> map, [String path = "TagValidationResultView"]) {
    _rejectUnknownFields(map, const <String>{"taxonomyReleaseId", "valid", "invalid"}, path);
    return TagValidationResultView(
      taxonomyReleaseId: _requiredString(map["taxonomyReleaseId"], '$path.taxonomyReleaseId'),
      valid: List<String>.unmodifiable(_requiredList(map["valid"], '$path.valid').asMap().entries.map((entry) => _requiredString(entry.value, '$path.valid' + '[${entry.key}]'))),
      invalid: List<String>.unmodifiable(_requiredList(map["invalid"], '$path.invalid').asMap().entries.map((entry) => _requiredString(entry.value, '$path.invalid' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "taxonomyReleaseId": taxonomyReleaseId,
    "valid": valid.map((value) => value).toList(growable: false),
    "invalid": invalid.map((value) => value).toList(growable: false),
  };
}

TagChildrenSlice decodeTagChildrenSlice(Object? response) =>
    TagChildrenSlice.fromWire(_requiredObject(response, "TagChildrenSlice"), "TagChildrenSlice");

TagFeedbackResultView decodeTagFeedbackResultView(Object? response) =>
    TagFeedbackResultView.fromWire(_requiredObject(response, "TagFeedbackResultView"), "TagFeedbackResultView");

TagResolveView decodeTagResolveView(Object? response) =>
    TagResolveView.fromWire(_requiredObject(response, "TagResolveView"), "TagResolveView");

TagValidationResultView decodeTagValidationResultView(Object? response) =>
    TagValidationResultView.fromWire(_requiredObject(response, "TagValidationResultView"), "TagValidationResultView");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
