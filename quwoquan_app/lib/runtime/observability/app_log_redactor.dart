// Code generated from object-local privacy.yaml via codegen_observability_catalog. DO NOT EDIT.

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
