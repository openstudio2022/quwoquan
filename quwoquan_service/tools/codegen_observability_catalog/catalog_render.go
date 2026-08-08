package main

import (
	"fmt"
	"go/format"
	"os"
	"sort"
	"strconv"
	"strings"
)

func renderGo(value catalog) string {
	var b strings.Builder
	b.WriteString("// Code generated from runtime_observability.yaml and object-local privacy.yaml. DO NOT EDIT.\n\n")
	b.WriteString("package runtimeobservability\n\n")
	b.WriteString("const ObservabilitySchema = " + strconv.Quote(value.Schema) + "\n\n")
	b.WriteString("type CatalogSignalMetadata struct {\n")
	b.WriteString("\tOwner string\n")
	b.WriteString("\tProducers []string\n")
	b.WriteString("\tLogKind string\n")
	b.WriteString("\tDefaultSeverity string\n")
	b.WriteString("\tEnvironments []string\n")
	b.WriteString("\tAttributeAllowlist []string\n")
	b.WriteString("\tCorrelationKeys []string\n")
	b.WriteString("\tBackend string\n")
	b.WriteString("\tRetentionDays int\n")
	b.WriteString("\tSampling string\n")
	b.WriteString("\tAlert string\n")
	b.WriteString("\tRunbook string\n")
	b.WriteString("\tPIIClassification string\n")
	b.WriteString("}\n\n")
	writeGoSet(&b, "CatalogLogKinds", value.LogKinds)
	writeGoSet(&b, "CatalogSeverityLevels", value.SeverityLevels)
	writeGoSet(&b, "CatalogSignals", signalIDs(value.Signals))
	writeGoSet(&b, "CatalogForbiddenFields", value.ForbiddenFields)
	writeGoStringMap(&b, "CatalogFailureCodes", value.FailureCodes)
	writeGoSet(&b, "CatalogForbiddenAttributeKeys", value.Privacy.ForbiddenAttributeKeys)
	writeGoSet(&b, "CatalogHighCardinalityMetricKeys", value.Privacy.HighCardinalityMetricKeys)
	b.WriteString("func init() {\n")
	b.WriteString("\tregisterCatalogFieldPrivacyPolicies([]CatalogFieldPrivacyPolicy{\n")
	for _, policy := range value.FieldPrivacyPolicies {
		b.WriteString("\t\t{ObjectID: " + strconv.Quote(policy.ObjectID) +
			", Field: " + strconv.Quote(policy.Field) +
			", Classification: " + strconv.Quote(policy.Classification) +
			", Action: " + strconv.Quote(policy.Action) +
			", MaskStrategy: " + strconv.Quote(policy.MaskStrategy) +
			", TruncateChars: " + strconv.Itoa(policy.TruncateChars) +
			", Explicit: " + strconv.FormatBool(policy.Explicit) +
			", Visibility: " + goStringSliceLiteral(policy.Visibility) + "},\n")
	}
	b.WriteString("\t})\n")
	b.WriteString("}\n\n")
	writeGoInt(&b, "CatalogMaxBatchItems", value.Limits.MaxBatchItems)
	writeGoInt(&b, "CatalogMaxCanonicalBodyBytes", value.Limits.MaxCanonicalBodyBytes)
	writeGoInt(&b, "CatalogMaxMessageBytes", value.Limits.MaxMessageBytes)
	writeGoInt(&b, "CatalogMaxAttributes", value.Limits.MaxAttributes)
	writeGoInt(&b, "CatalogMaxAttributesBytes", value.Limits.MaxAttributesBytes)
	writeGoInt(&b, "CatalogMaxAttributeKeyLength", value.Limits.MaxAttributeKeyLength)
	writeGoInt(&b, "CatalogMaxAttributeValueLength", value.Limits.MaxAttributeValueLength)
	writeGoInt(&b, "CatalogRawRetentionDays", value.Limits.RawRetentionDays)
	writeGoInt(&b, "CatalogAppBufferCapacity", value.Delivery.AppBufferCapacity)
	writeGoInt(&b, "CatalogAppDeadLetterCapacity", value.Delivery.AppDeadLetterCapacity)
	writeGoInt(&b, "CatalogServiceSpoolMaxBatches", value.Delivery.ServiceSpoolMaxBatches)
	writeGoInt(&b, "CatalogServiceDLQMaxBatches", value.Delivery.ServiceDLQMaxBatches)
	writeGoInt(&b, "CatalogDeliveryTTLHours", value.Delivery.TTLHours)
	writeGoInt(&b, "CatalogRetryBaseSeconds", value.Delivery.RetryBaseSeconds)
	writeGoInt(&b, "CatalogRetryMaxSeconds", value.Delivery.RetryMaxSeconds)
	writeGoInt(&b, "CatalogRetryMaxExponent", value.Delivery.RetryMaxExponent)
	writeGoInt(&b, "CatalogRetryJitterPercent", value.Delivery.RetryJitterPercent)
	writeGoSlice(&b, "CatalogEnvelopeRequiredFields", value.Envelope.Required)
	writeGoSlice(&b, "CatalogEnvelopeOptionalFields", value.Envelope.Optional)
	writeGoSlice(&b, "CatalogResourceRequiredFields", value.Envelope.ResourceRequired)
	writeGoSlice(&b, "CatalogResourceOptionalFields", value.Envelope.ResourceOptional)
	writeGoSlice(&b, "CatalogCorrelationOptionalFields", value.Envelope.CorrelationOptional)
	b.WriteString("var CatalogFieldOrder = map[string][]string{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("\t" + strconv.Quote(kind) + ": {")
		for index, field := range value.KindFields[kind].Ordered {
			if index > 0 {
				b.WriteString(", ")
			}
			b.WriteString(strconv.Quote(field))
		}
		b.WriteString("},\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogRequiredFields = map[string]map[string]struct{}{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("\t" + strconv.Quote(kind) + ": {")
		for index, field := range value.KindFields[kind].Required {
			if index > 0 {
				b.WriteString(", ")
			}
			b.WriteString(strconv.Quote(field) + ": {}")
		}
		b.WriteString("},\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogSignalLogKinds = map[string]string{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogSignalDefaultSeverities = map[string]string{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("\nvar CatalogSignalRegistry = map[string]CatalogSignalMetadata{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("\t\tOwner: " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("\t\tProducers: " + goStringSliceLiteral(item.Producers) + ",\n")
		b.WriteString("\t\tLogKind: " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("\t\tDefaultSeverity: " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("\t\tEnvironments: " + goStringSliceLiteral(item.Environments) + ",\n")
		b.WriteString("\t\tAttributeAllowlist: " + goStringSliceLiteral(item.AttributeAllowlist) + ",\n")
		b.WriteString("\t\tCorrelationKeys: " + goStringSliceLiteral(item.CorrelationKeys) + ",\n")
		b.WriteString("\t\tBackend: " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("\t\tRetentionDays: " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("\t\tSampling: " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("\t\tAlert: " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("\t\tRunbook: " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("\t\tPIIClassification: " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("\t},\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func mustFormatGo(source string) string {
	formatted, err := format.Source([]byte(source))
	exitIf(err)
	return string(formatted)
}

func writeGoSet(b *strings.Builder, name string, values []string) {
	b.WriteString("var " + name + " = map[string]struct{}{\n")
	for _, value := range values {
		b.WriteString("\t" + strconv.Quote(value) + ": {},\n")
	}
	b.WriteString("}\n\n")
}

func writeGoSlice(b *strings.Builder, name string, values []string) {
	b.WriteString("var " + name + " = []string{")
	for index, value := range values {
		if index > 0 {
			b.WriteString(", ")
		}
		b.WriteString(strconv.Quote(value))
	}
	b.WriteString("}\n\n")
}

func writeGoInt(b *strings.Builder, name string, value int) {
	b.WriteString("const " + name + " = " + strconv.Itoa(value) + "\n\n")
}

func writeGoStringMap(b *strings.Builder, name string, values map[string]string) {
	b.WriteString("var " + name + " = map[string]string{\n")
	for _, key := range sortedKeys(values) {
		b.WriteString("\t" + strconv.Quote(key) + ": " + strconv.Quote(values[key]) + ",\n")
	}
	b.WriteString("}\n\n")
}

func goStringSliceLiteral(values []string) string {
	if len(values) == 0 {
		return "nil"
	}
	return "[]string{" + joinQuoted(values, strconv.Quote) + "}"
}

func renderDart(value catalog) string {
	var b strings.Builder
	b.WriteString("// Code generated from runtime_observability.yaml and object-local privacy.yaml. DO NOT EDIT.\n\n")
	b.WriteString("final class RuntimeLogFieldPrivacyPolicy {\n")
	b.WriteString("  const RuntimeLogFieldPrivacyPolicy({required this.objectId, required this.field, required this.classification, required this.action, this.maskStrategy = '', this.truncateChars = 0, required this.explicit, required this.visibility});\n")
	b.WriteString("  final String objectId;\n")
	b.WriteString("  final String field;\n")
	b.WriteString("  final String classification;\n")
	b.WriteString("  final String action;\n")
	b.WriteString("  final String maskStrategy;\n")
	b.WriteString("  final int truncateChars;\n")
	b.WriteString("  final bool explicit;\n")
	b.WriteString("  final List<String> visibility;\n")
	b.WriteString("}\n\n")
	b.WriteString("final class RuntimeLogSignalMetadata {\n")
	b.WriteString("  const RuntimeLogSignalMetadata({required this.owner, required this.producers, required this.logKind, required this.defaultSeverity, required this.environments, required this.attributeAllowlist, required this.correlationKeys, required this.backend, required this.retentionDays, required this.sampling, required this.alert, required this.runbook, required this.piiClassification});\n")
	b.WriteString("  final String owner;\n")
	b.WriteString("  final List<String> producers;\n")
	b.WriteString("  final String logKind;\n")
	b.WriteString("  final String defaultSeverity;\n")
	b.WriteString("  final List<String> environments;\n")
	b.WriteString("  final List<String> attributeAllowlist;\n")
	b.WriteString("  final List<String> correlationKeys;\n")
	b.WriteString("  final String backend;\n")
	b.WriteString("  final int retentionDays;\n")
	b.WriteString("  final String sampling;\n")
	b.WriteString("  final String alert;\n")
	b.WriteString("  final String runbook;\n")
	b.WriteString("  final String piiClassification;\n")
	b.WriteString("}\n\n")
	b.WriteString("abstract final class RuntimeLogCatalog {\n")
	b.WriteString("  static const String schema = " + dartQuote(value.Schema) + ";\n")
	b.WriteString("  static const Set<String> logKinds = <String>{" + joinQuoted(value.LogKinds, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> severityLevels = <String>{" + joinQuoted(value.SeverityLevels, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> signals = <String>{" + joinQuoted(signalIDs(value.Signals), dartQuote) + "};\n")
	b.WriteString("  static const Set<String> forbiddenFields = <String>{" + joinQuoted(value.ForbiddenFields, dartQuote) + "};\n")
	b.WriteString("  static const Map<String, String> failureCodes = <String, String>{\n")
	for _, key := range sortedKeys(value.FailureCodes) {
		b.WriteString("    " + dartQuote(key) + ": " + dartQuote(value.FailureCodes[key]) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Set<String> forbiddenAttributeKeys = <String>{" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> highCardinalityMetricKeys = <String>{" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, dartQuote) + "};\n")
	b.WriteString("  static const List<RuntimeLogFieldPrivacyPolicy> fieldPrivacyPolicies = <RuntimeLogFieldPrivacyPolicy>[\n")
	for _, policy := range value.FieldPrivacyPolicies {
		b.WriteString("    RuntimeLogFieldPrivacyPolicy(objectId: " + dartQuote(policy.ObjectID) +
			", field: " + dartQuote(policy.Field) +
			", classification: " + dartQuote(policy.Classification) +
			", action: " + dartQuote(policy.Action) +
			", maskStrategy: " + dartQuote(policy.MaskStrategy) +
			", truncateChars: " + strconv.Itoa(policy.TruncateChars) +
			", explicit: " + strconv.FormatBool(policy.Explicit) +
			", visibility: <String>[" + joinQuoted(policy.Visibility, dartQuote) + "]),\n")
	}
	b.WriteString("  ];\n")
	b.WriteString("  static const Set<String> resourceVersionFields = <String>{" + joinQuoted(value.ResourceVersionFields, dartQuote) + "};\n")
	b.WriteString("  static const int maxBatchItems = " + strconv.Itoa(value.Limits.MaxBatchItems) + ";\n")
	b.WriteString("  static const int maxCanonicalBodyBytes = " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + ";\n")
	b.WriteString("  static const int maxMessageBytes = " + strconv.Itoa(value.Limits.MaxMessageBytes) + ";\n")
	b.WriteString("  static const int maxAttributes = " + strconv.Itoa(value.Limits.MaxAttributes) + ";\n")
	b.WriteString("  static const int maxAttributesBytes = " + strconv.Itoa(value.Limits.MaxAttributesBytes) + ";\n")
	b.WriteString("  static const int maxAttributeKeyLength = " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + ";\n")
	b.WriteString("  static const int maxAttributeValueLength = " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + ";\n")
	b.WriteString("  static const int rawRetentionDays = " + strconv.Itoa(value.Limits.RawRetentionDays) + ";\n")
	b.WriteString("  static const int appBufferCapacity = " + strconv.Itoa(value.Delivery.AppBufferCapacity) + ";\n")
	b.WriteString("  static const int appDeadLetterCapacity = " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + ";\n")
	b.WriteString("  static const int serviceSpoolMaxBatches = " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + ";\n")
	b.WriteString("  static const int serviceDlqMaxBatches = " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + ";\n")
	b.WriteString("  static const int deliveryTtlHours = " + strconv.Itoa(value.Delivery.TTLHours) + ";\n")
	b.WriteString("  static const int retryBaseSeconds = " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + ";\n")
	b.WriteString("  static const int retryMaxSeconds = " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + ";\n")
	b.WriteString("  static const int retryMaxExponent = " + strconv.Itoa(value.Delivery.RetryMaxExponent) + ";\n")
	b.WriteString("  static const int retryJitterPercent = " + strconv.Itoa(value.Delivery.RetryJitterPercent) + ";\n")
	b.WriteString("  static const List<String> envelopeRequiredFields = <String>[" + joinQuoted(value.Envelope.Required, dartQuote) + "];\n")
	b.WriteString("  static const Set<String> envelopeOptionalFields = <String>{" + joinQuoted(value.Envelope.Optional, dartQuote) + "};\n")
	b.WriteString("  static const List<String> resourceRequiredFields = <String>[" + joinQuoted(value.Envelope.ResourceRequired, dartQuote) + "];\n")
	b.WriteString("  static const Set<String> resourceOptionalFields = <String>{" + joinQuoted(value.Envelope.ResourceOptional, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> correlationOptionalFields = <String>{" + joinQuoted(value.Envelope.CorrelationOptional, dartQuote) + "};\n")
	b.WriteString("  static const Map<String, List<String>> fieldOrder = <String, List<String>>{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + dartQuote(kind) + ": <String>[" + joinQuoted(value.KindFields[kind].Ordered, dartQuote) + "],\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, String> signalKinds = <String, String>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": " + dartQuote(item.LogKind) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, String> signalDefaultSeverities = <String, String>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": " + dartQuote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, RuntimeLogSignalMetadata> signalRegistry = <String, RuntimeLogSignalMetadata>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": RuntimeLogSignalMetadata(owner: " + dartQuote(item.Owner) + ", producers: <String>[" + joinQuoted(item.Producers, dartQuote) + "], logKind: " + dartQuote(item.LogKind) + ", defaultSeverity: " + dartQuote(item.DefaultSeverity) + ", environments: <String>[" + joinQuoted(item.Environments, dartQuote) + "], attributeAllowlist: <String>[" + joinQuoted(item.AttributeAllowlist, dartQuote) + "], correlationKeys: <String>[" + joinQuoted(item.CorrelationKeys, dartQuote) + "], backend: " + dartQuote(item.Backend) + ", retentionDays: " + strconv.Itoa(item.RetentionDays) + ", sampling: " + dartQuote(item.Sampling) + ", alert: " + dartQuote(item.Alert) + ", runbook: " + dartQuote(item.Runbook) + ", piiClassification: " + dartQuote(item.PIIClassification) + "),\n")
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderAppLogRedactor() string {
	return `// Code generated from object-local privacy.yaml via codegen_observability_catalog. DO NOT EDIT.

import 'package:quwoquan_app/runtime/observability/generated/runtime_log_catalog.g.dart';

class AppLogRedactor {
  const AppLogRedactor();

  static const String _masked = '***';
  static const Object _drop = Object();

  Map<String, dynamic> redactMap(
    Map<String, dynamic> input, {
    String operationId = '',
  }) {
    final objectId = _objectIdFromOperationId(operationId);
    final out = <String, dynamic>{};
    input.forEach((key, value) {
      final redacted = _redactValue(
        objectId: objectId,
        key: key,
        value: value,
      );
      if (!identical(redacted, _drop)) out[key] = redacted;
    });
    return out;
  }

  String redactText(String input) {
    var value = input;
    value = value.replaceAll(
      RegExp(r'\bBearer\s+[A-Za-z0-9._~+/=-]+', caseSensitive: false),
      'Bearer $_masked',
    );
    value = value.replaceAllMapped(
      RegExp(
        r'([?&](?:access_token|token|authcode|authorization|signature|'
        r'x-amz-signature|x-amz-credential|secret)=)[^&#\s]+',
        caseSensitive: false,
      ),
      (match) => '${match.group(1)}$_masked',
    );
    value = value.replaceAllMapped(
      RegExp(
        r'((?:"|\\")?(?:access_token|token|authcode|'
        r'signature|secret)(?:"|\\")?\s*[:=]\s*(?:"|\\")?)[^",}&\s]+',
        caseSensitive: false,
      ),
      (match) => '${match.group(1)}$_masked',
    );
    return value;
  }

  dynamic _redactValue({
    required String objectId,
    required String key,
    required dynamic value,
  }) {
    final policy = _policyFor(objectId, key);
    if (policy != null) {
      if (!_visibilityAllowsApp(policy.visibility)) return _drop;
      final governed = _applyPolicy(policy, value);
      if (identical(governed, _drop)) return _drop;
      value = governed;
      if (policy.action != 'allow') return value;
    }
    if (_isCatalogSensitiveKey(key)) return _masked;
    if (value is Map) {
      final map = <String, dynamic>{};
      value.forEach((nestedKey, nestedValue) {
        final redacted = _redactValue(
          objectId: objectId,
          key: '$nestedKey',
          value: nestedValue,
        );
        if (!identical(redacted, _drop)) map['$nestedKey'] = redacted;
      });
      return map;
    }
    if (value is Iterable) {
      return value
          .map(
            (item) => _redactValue(
              objectId: objectId,
              key: key,
              value: item,
            ),
          )
          .where((item) => !identical(item, _drop))
          .toList(growable: false);
    }
    if (value is String) {
      if (_looksSensitiveText(value)) return _masked;
      return redactText(value);
    }
    return value;
  }

  dynamic _applyPolicy(RuntimeLogFieldPrivacyPolicy policy, dynamic value) {
    switch (policy.action) {
      case 'allow':
        return value;
      case 'drop':
        return _drop;
      case 'mask':
        return _coarseMask(value, policy.maskStrategy);
      case 'truncate':
        final text = redactText('$value');
        if (text.length <= policy.truncateChars) return text;
        return '${text.substring(0, policy.truncateChars)}…';
      case 'count_only':
        if (value is Map || value is Iterable || value is String) {
          return value.length;
        }
        return 0;
      case 'drop_if_gt_100chars':
        final text = '$value';
        return text.length > 100 ? _drop : redactText(text);
      default:
        return _drop;
    }
  }

  dynamic _coarseMask(dynamic value, String strategy) {
    if (value is! Map) return _masked;
    final allowed = strategy == 'city_level_only'
        ? const <String>{'country', 'countryName', 'province', 'provinceName', 'city', 'cityName'}
        : const <String>{'country', 'countryName', 'province', 'provinceName'};
    final out = <String, dynamic>{};
    value.forEach((key, item) {
      if (allowed.contains('$key')) out['$key'] = redactText('$item');
    });
    return out.isEmpty ? _masked : out;
  }

  RuntimeLogFieldPrivacyPolicy? _policyFor(String objectId, String key) {
    final normalized = _normalizeKey(key);
    RuntimeLogFieldPrivacyPolicy? fallback;
    for (final policy in RuntimeLogCatalog.fieldPrivacyPolicies) {
      if (_normalizeKey(policy.field) != normalized) continue;
      if (objectId.isNotEmpty && policy.objectId == objectId) return policy;
      if (objectId.isEmpty && !policy.explicit) continue;
      if (fallback == null || _policyRank(policy) > _policyRank(fallback)) {
        fallback = policy;
      } else if (_policyRank(policy) == _policyRank(fallback) &&
          policy.action == 'truncate' &&
          policy.truncateChars < fallback.truncateChars) {
        fallback = policy;
      }
    }
    return fallback;
  }

  int _policyRank(RuntimeLogFieldPrivacyPolicy policy) {
    switch (policy.action) {
      case 'drop':
        return 6;
      case 'drop_if_gt_100chars':
        return 5;
      case 'mask':
        return 4;
      case 'count_only':
        return 3;
      case 'truncate':
        return 2;
      case 'allow':
        return 1;
      default:
        return 7;
    }
  }

  bool _visibilityAllowsApp(List<String> visibility) {
    if (visibility.isEmpty) return true;
    return visibility.any(
      (audience) => audience == 'app' || audience == 'all',
    );
  }

  bool _isCatalogSensitiveKey(String key) {
    final normalized = _normalizeKey(key);
    return RuntimeLogCatalog.forbiddenAttributeKeys.any((blocked) {
      final normalizedBlocked = _normalizeKey(blocked);
      return normalized == normalizedBlocked ||
          (normalizedBlocked != 'ip' && normalized.contains(normalizedBlocked));
    });
  }

  String _normalizeKey(String value) =>
      value.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

  String _objectIdFromOperationId(String operationId) {
    final parts = operationId.trim().split('.');
    return parts.length < 3 ? '' : '${parts[0]}.${parts[1]}';
  }

  bool _looksSensitiveText(String text) {
    final lowered = text.toLowerCase();
    if (lowered.startsWith('bearer ')) return true;
    return RegExp(r'^[A-Za-z0-9_\-]{24,}$').hasMatch(text);
  }
}
`
}

func renderPython(value catalog) string {
	var b strings.Builder
	b.WriteString("# Code generated from runtime_observability.yaml and object-local privacy.yaml. DO NOT EDIT.\n\n")
	b.WriteString("OBSERVABILITY_SCHEMA = " + strconv.Quote(value.Schema) + "\n")
	b.WriteString("LOG_KINDS = frozenset((" + joinQuoted(value.LogKinds, strconv.Quote) + ",))\n")
	b.WriteString("LEVELS = frozenset((" + joinQuoted(value.SeverityLevels, strconv.Quote) + ",))\n")
	b.WriteString("SIGNALS = frozenset((" + joinQuoted(signalIDs(value.Signals), strconv.Quote) + ",))\n")
	b.WriteString("FORBIDDEN_FIELDS = frozenset((" + joinQuoted(value.ForbiddenFields, strconv.Quote) + ",))\n")
	b.WriteString("FAILURE_CODES = {\n")
	for _, key := range sortedKeys(value.FailureCodes) {
		b.WriteString("    " + strconv.Quote(key) + ": " + strconv.Quote(value.FailureCodes[key]) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("FORBIDDEN_ATTRIBUTE_KEYS = frozenset((" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, strconv.Quote) + ",))\n")
	b.WriteString("HIGH_CARDINALITY_METRIC_KEYS = frozenset((" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, strconv.Quote) + ",))\n")
	b.WriteString("FIELD_PRIVACY_POLICIES = (\n")
	for _, policy := range value.FieldPrivacyPolicies {
		b.WriteString("    {")
		b.WriteString(strconv.Quote("objectId") + ": " + strconv.Quote(policy.ObjectID) + ", ")
		b.WriteString(strconv.Quote("field") + ": " + strconv.Quote(policy.Field) + ", ")
		b.WriteString(strconv.Quote("classification") + ": " + strconv.Quote(policy.Classification) + ", ")
		b.WriteString(strconv.Quote("action") + ": " + strconv.Quote(policy.Action) + ", ")
		b.WriteString(strconv.Quote("maskStrategy") + ": " + strconv.Quote(policy.MaskStrategy) + ", ")
		b.WriteString(strconv.Quote("truncateChars") + ": " + strconv.Itoa(policy.TruncateChars) + ", ")
		b.WriteString(strconv.Quote("explicit") + ": " + pythonBool(policy.Explicit) + ", ")
		b.WriteString(strconv.Quote("visibility") + ": " + pythonTupleLiteral(policy.Visibility) + "},\n")
	}
	b.WriteString(")\n")
	b.WriteString("RESOURCE_VERSION_FIELDS = frozenset((" + joinQuoted(value.ResourceVersionFields, strconv.Quote) + ",))\n")
	b.WriteString("MAX_BATCH_ITEMS = " + strconv.Itoa(value.Limits.MaxBatchItems) + "\n")
	b.WriteString("MAX_CANONICAL_BODY_BYTES = " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + "\n")
	b.WriteString("MAX_MESSAGE_BYTES = " + strconv.Itoa(value.Limits.MaxMessageBytes) + "\n")
	b.WriteString("MAX_ATTRIBUTES = " + strconv.Itoa(value.Limits.MaxAttributes) + "\n")
	b.WriteString("MAX_ATTRIBUTES_BYTES = " + strconv.Itoa(value.Limits.MaxAttributesBytes) + "\n")
	b.WriteString("MAX_ATTRIBUTE_KEY_LENGTH = " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + "\n")
	b.WriteString("MAX_ATTRIBUTE_VALUE_LENGTH = " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + "\n")
	b.WriteString("RAW_RETENTION_DAYS = " + strconv.Itoa(value.Limits.RawRetentionDays) + "\n")
	b.WriteString("APP_BUFFER_CAPACITY = " + strconv.Itoa(value.Delivery.AppBufferCapacity) + "\n")
	b.WriteString("APP_DEAD_LETTER_CAPACITY = " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + "\n")
	b.WriteString("SERVICE_SPOOL_MAX_BATCHES = " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + "\n")
	b.WriteString("SERVICE_DLQ_MAX_BATCHES = " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + "\n")
	b.WriteString("DELIVERY_TTL_HOURS = " + strconv.Itoa(value.Delivery.TTLHours) + "\n")
	b.WriteString("RETRY_BASE_SECONDS = " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + "\n")
	b.WriteString("RETRY_MAX_SECONDS = " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + "\n")
	b.WriteString("RETRY_MAX_EXPONENT = " + strconv.Itoa(value.Delivery.RetryMaxExponent) + "\n")
	b.WriteString("RETRY_JITTER_PERCENT = " + strconv.Itoa(value.Delivery.RetryJitterPercent) + "\n")
	b.WriteString("ENVELOPE_REQUIRED_FIELDS = (" + joinQuoted(value.Envelope.Required, strconv.Quote) + ",)\n")
	b.WriteString("ENVELOPE_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.Optional, strconv.Quote) + ",))\n")
	b.WriteString("RESOURCE_REQUIRED_FIELDS = (" + joinQuoted(value.Envelope.ResourceRequired, strconv.Quote) + ",)\n")
	b.WriteString("RESOURCE_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.ResourceOptional, strconv.Quote) + ",))\n")
	b.WriteString("CORRELATION_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.CorrelationOptional, strconv.Quote) + ",))\n")
	b.WriteString("LOG_FIELD_ORDER = {\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": (" + joinQuoted(value.KindFields[kind].Ordered, strconv.Quote) + ",),\n")
	}
	b.WriteString("}\n")
	b.WriteString("REQUIRED_KIND_FIELDS = {\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": frozenset((" + joinQuoted(value.KindFields[kind].Required, strconv.Quote) + ",)),\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_LOG_KINDS = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_DEFAULT_SEVERITIES = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_REGISTRY = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("        \"owner\": " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("        \"producers\": (" + joinQuoted(item.Producers, strconv.Quote) + ",),\n")
		b.WriteString("        \"logKind\": " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("        \"defaultSeverity\": " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("        \"environments\": (" + joinQuoted(item.Environments, strconv.Quote) + ",),\n")
		b.WriteString("        \"attributeAllowlist\": (" + joinQuoted(item.AttributeAllowlist, strconv.Quote) + ",),\n")
		b.WriteString("        \"correlationKeys\": (" + joinQuoted(item.CorrelationKeys, strconv.Quote) + ",),\n")
		b.WriteString("        \"backend\": " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("        \"retentionDays\": " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("        \"sampling\": " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("        \"alert\": " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("        \"runbook\": " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("        \"piiClassification\": " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("    },\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func renderTypeScript(value catalog) string {
	return strings.Join([]string{
		"// Code generated from runtime_observability.yaml and object-local privacy.yaml. DO NOT EDIT.",
		"",
		"export const runtimeLogCatalog = {",
		"  schema: " + strconv.Quote(value.Schema) + ",",
		"  logKinds: [" + joinQuoted(value.LogKinds, strconv.Quote) + "] as const,",
		"  severityLevels: [" + joinQuoted(value.SeverityLevels, strconv.Quote) + "] as const,",
		"  signals: [" + joinQuoted(signalIDs(value.Signals), strconv.Quote) + "] as const,",
		"  forbiddenFields: [" + joinQuoted(value.ForbiddenFields, strconv.Quote) + "] as const,",
		"  failureCodes: {",
		renderTypeScriptStringMap(value.FailureCodes),
		"  } as const,",
		"  forbiddenAttributeKeys: [" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, strconv.Quote) + "] as const,",
		"  highCardinalityMetricKeys: [" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, strconv.Quote) + "] as const,",
		"  fieldPrivacyPolicies: [",
		renderTypeScriptFieldPrivacyPolicies(value),
		"  ] as const,",
		"  resourceVersionFields: [" + joinQuoted(value.ResourceVersionFields, strconv.Quote) + "] as const,",
		"  maxBatchItems: " + strconv.Itoa(value.Limits.MaxBatchItems) + ",",
		"  maxCanonicalBodyBytes: " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + ",",
		"  maxMessageBytes: " + strconv.Itoa(value.Limits.MaxMessageBytes) + ",",
		"  maxAttributes: " + strconv.Itoa(value.Limits.MaxAttributes) + ",",
		"  maxAttributesBytes: " + strconv.Itoa(value.Limits.MaxAttributesBytes) + ",",
		"  maxAttributeKeyLength: " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + ",",
		"  maxAttributeValueLength: " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + ",",
		"  rawRetentionDays: " + strconv.Itoa(value.Limits.RawRetentionDays) + ",",
		"  appBufferCapacity: " + strconv.Itoa(value.Delivery.AppBufferCapacity) + ",",
		"  appDeadLetterCapacity: " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + ",",
		"  serviceSpoolMaxBatches: " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + ",",
		"  serviceDlqMaxBatches: " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + ",",
		"  deliveryTtlHours: " + strconv.Itoa(value.Delivery.TTLHours) + ",",
		"  retryBaseSeconds: " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + ",",
		"  retryMaxSeconds: " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + ",",
		"  retryMaxExponent: " + strconv.Itoa(value.Delivery.RetryMaxExponent) + ",",
		"  retryJitterPercent: " + strconv.Itoa(value.Delivery.RetryJitterPercent) + ",",
		"  envelopeRequiredFields: [" + joinQuoted(value.Envelope.Required, strconv.Quote) + "] as const,",
		"  envelopeOptionalFields: [" + joinQuoted(value.Envelope.Optional, strconv.Quote) + "] as const,",
		"  resourceRequiredFields: [" + joinQuoted(value.Envelope.ResourceRequired, strconv.Quote) + "] as const,",
		"  resourceOptionalFields: [" + joinQuoted(value.Envelope.ResourceOptional, strconv.Quote) + "] as const,",
		"  correlationOptionalFields: [" + joinQuoted(value.Envelope.CorrelationOptional, strconv.Quote) + "] as const,",
		"  fieldOrder: {",
		renderTypeScriptFieldOrders(value),
		"  } as const,",
		"  signalKinds: {",
		renderTypeScriptSignalKinds(value),
		"  } as const,",
		"  signalDefaultSeverities: {",
		renderTypeScriptSignalDefaultSeverities(value),
		"  } as const,",
		"  signalRegistry: {",
		renderTypeScriptSignalRegistry(value),
		"  } as const,",
		"} as const;",
		"",
		"export type RuntimeLogKind = (typeof runtimeLogCatalog.logKinds)[number];",
		"export type RuntimeLogSeverity = (typeof runtimeLogCatalog.severityLevels)[number];",
		"export type RuntimeLogSignal = (typeof runtimeLogCatalog.signals)[number];",
		"",
	}, "\n")
}

func renderTypeScriptFieldPrivacyPolicies(value catalog) string {
	var b strings.Builder
	for _, policy := range value.FieldPrivacyPolicies {
		b.WriteString("    {objectId: " + strconv.Quote(policy.ObjectID) +
			", field: " + strconv.Quote(policy.Field) +
			", classification: " + strconv.Quote(policy.Classification) +
			", action: " + strconv.Quote(policy.Action) +
			", maskStrategy: " + strconv.Quote(policy.MaskStrategy) +
			", truncateChars: " + strconv.Itoa(policy.TruncateChars) +
			", explicit: " + strconv.FormatBool(policy.Explicit) +
			", visibility: [" + joinQuoted(policy.Visibility, strconv.Quote) + "]},\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptFieldOrders(value catalog) string {
	var b strings.Builder
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": [" + joinQuoted(value.KindFields[kind].Ordered, strconv.Quote) + "],\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalKinds(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalDefaultSeverities(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptStringMap(values map[string]string) string {
	var b strings.Builder
	for _, key := range sortedKeys(values) {
		b.WriteString("    " + strconv.Quote(key) + ": " + strconv.Quote(values[key]) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalRegistry(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("      owner: " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("      producers: [" + joinQuoted(item.Producers, strconv.Quote) + "],\n")
		b.WriteString("      logKind: " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("      defaultSeverity: " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("      environments: [" + joinQuoted(item.Environments, strconv.Quote) + "],\n")
		b.WriteString("      attributeAllowlist: [" + joinQuoted(item.AttributeAllowlist, strconv.Quote) + "],\n")
		b.WriteString("      correlationKeys: [" + joinQuoted(item.CorrelationKeys, strconv.Quote) + "],\n")
		b.WriteString("      backend: " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("      retentionDays: " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("      sampling: " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("      alert: " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("      runbook: " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("      piiClassification: " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("    },\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func signalIDs(values []signal) []string {
	out := make([]string, 0, len(values))
	for _, item := range values {
		out = append(out, item.ID)
	}
	sort.Strings(out)
	return out
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func sortedSignals(values []signal) []signal {
	out := append([]signal(nil), values...)
	sort.Slice(out, func(left, right int) bool {
		return out[left].ID < out[right].ID
	})
	return out
}

func sortedKeys(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func joinQuoted(values []string, quote func(string) string) string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, quote(value))
	}
	return strings.Join(out, ", ")
}

func pythonBool(value bool) string {
	if value {
		return "True"
	}
	return "False"
}

func pythonTupleLiteral(values []string) string {
	if len(values) == 0 {
		return "()"
	}
	return "(" + joinQuoted(values, strconv.Quote) + ",)"
}

func dartQuote(value string) string {
	return "'" + strings.ReplaceAll(strings.ReplaceAll(value, `\`, `\\`), "'", `\'`) + "'"
}

func exitIf(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
