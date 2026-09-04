package main

import "strings"

func renderDomainDecoderHelpers(
	output *strings.Builder,
	models map[string]requestModelSpec,
	topLevelObjectDecoder bool,
) {
	used := map[string]bool{}
	var record func(field fieldDef)
	record = func(field fieldDef) {
		metaType := strings.TrimSpace(field.Type)
		if strings.HasPrefix(metaType, "[]") {
			used["list"] = true
			if field.MaxItems > 0 {
				used["boundedList"] = true
			}
			record(responseFieldListItem(field))
			return
		}
		switch metaType {
		case "string", "tag_ref", "ObjectId", "uuid", "identifier":
			used["string"] = true
			if strings.TrimSpace(field.Format) == canonicalSHA256Format {
				used["nonBlankString"] = true
				used["canonicalSha256Digest"] = true
				break
			}
			if hasRequestConstraint(field, "NOT_BLANK") {
				used["nonBlankString"] = true
			}
		case "time":
			used["string"] = true
			used["timeOfDay"] = true
		case "url":
			used["string"] = true
			used["nonBlankString"] = true
			used["url"] = true
		case "timestamp", "datetime", "date":
			used["string"] = true
			used["timestamp"] = true
		case "int", "int32", "int64", "long":
			used["int"] = true
			if responseIntegerUsesBoundedDecoder(field) {
				used["boundedInt"] = true
				break
			}
			if hasRequestConstraint(field, "NON_NEGATIVE") {
				used["nonNegativeInt"] = true
			}
			if hasRequestConstraint(field, "MIN_1") {
				used["positiveInt"] = true
			}
		case "float", "float32", "float64", "double":
			used["double"] = true
		case "bool", "boolean":
			used["bool"] = true
		case "object", "json", "jsonb":
			used["object"] = true
		default:
			if metaType != "" && metaType != "enum" {
				used["object"] = true
			}
		}
	}
	for _, model := range models {
		for _, field := range model.Fields {
			record(field)
		}
		if groups, err := responseCoPresentFieldGroups(model); err == nil &&
			len(groups) > 0 {
			used["coPresentFields"] = true
		}
	}
	if used["object"] || topLevelObjectDecoder {
		output.WriteString(`Map<String, Object?> _requiredObject(Object? value, String path) {
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
`)
	}

	output.WriteString(`
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
`)

	if used["string"] {
		output.WriteString(`
String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}
`)
	}

	if used["nonBlankString"] {
		output.WriteString(`
String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}
`)
	}

	if used["timeOfDay"] {
		output.WriteString(`
String _requiredTimeOfDay(Object? value, String path) {
  final result = _requiredString(value, path);
  if (!RegExp(r'^([01][0-9]|2[0-3]):[0-5][0-9]$').hasMatch(result)) {
    throw FormatException('$path must be a HH:MM wall-clock time');
  }
  return result;
}
`)
	}

	if used["url"] {
		output.WriteString(`
Uri _requiredUri(Object? value, String path) {
  final raw = _requiredNonBlankString(value, path);
  final parsed = Uri.tryParse(raw);
  if (parsed == null || !parsed.hasScheme) {
    throw FormatException('$path must be an absolute URI');
  }
  return parsed;
}
`)
	}

	if used["timestamp"] {
		output.WriteString(`
DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}
`)
	}

	if used["int"] {
		output.WriteString(`
int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}
`)
	}

	if used["nonNegativeInt"] {
		output.WriteString(`
int _requiredNonNegativeInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 0) {
    throw FormatException('$path must not be negative');
  }
  return result;
}
`)
	}

	if used["positiveInt"] {
		output.WriteString(`
int _requiredPositiveInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 1) {
    throw FormatException('$path must be positive');
  }
  return result;
}
`)
	}

	if used["boundedInt"] {
		output.WriteString(`
int _requiredBoundedInt(
  Object? value,
  String path, {
  int? min,
  int? max,
}) {
  final result = _requiredInt(value, path);
  if (min != null && result < min) {
    throw FormatException('$path must be at least $min');
  }
  if (max != null && result > max) {
    throw FormatException('$path must not exceed $max');
  }
  return result;
}
`)
	}

	if used["double"] {
		output.WriteString(`
double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}
`)
	}

	if used["bool"] {
		output.WriteString(`
bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}
`)
	}

	if used["list"] {
		output.WriteString(`
List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
`)
	}

	if used["boundedList"] {
		output.WriteString(`
List<Object?> _requiredBoundedList(
  Object? value,
  String path, {
  required int max,
}) {
  final result = _requiredList(value, path);
  if (result.length > max) {
    throw FormatException('$path must not contain more than $max items');
  }
  return result;
}
`)
	}

	if used["canonicalSha256Digest"] {
		output.WriteString(`
String _requiredCanonicalSha256Digest(Object? value, String path) {
  final result = _requiredNonBlankString(value, path);
  if (!isCanonicalSha256Digest(result)) {
    throw FormatException('$path must be a canonical sha256 digest');
  }
  return result;
}
`)
	}

	if used["coPresentFields"] {
		output.WriteString(`
void _requireCoPresentFields(
  Map<String, Object?> value,
  Set<String> fields,
  String path,
) {
  final present = fields.where((field) => value[field] != null).length;
  if (present != 0 && present != fields.length) {
    throw FormatException(
      '$path requires ${fields.join(', ')} to be present together',
    );
  }
}
`)
	}
}
