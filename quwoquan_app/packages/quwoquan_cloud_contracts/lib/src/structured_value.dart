/// JSON 扩展字段的纯 Dart 表达，避免合同调用方接触 dynamic Map。
sealed class CloudStructuredValue {
  const CloudStructuredValue();
}

final class CloudStructuredObject extends CloudStructuredValue {
  CloudStructuredObject(Map<String, CloudStructuredValue> fields)
    : fields = Map<String, CloudStructuredValue>.unmodifiable(fields);

  final Map<String, CloudStructuredValue> fields;
}

final class CloudStructuredArray extends CloudStructuredValue {
  CloudStructuredArray(Iterable<CloudStructuredValue> values)
    : values = List<CloudStructuredValue>.unmodifiable(values);

  final List<CloudStructuredValue> values;
}

final class CloudStructuredText extends CloudStructuredValue {
  const CloudStructuredText(this.value);

  final String value;
}

final class CloudStructuredNumber extends CloudStructuredValue {
  const CloudStructuredNumber(this.value);

  final num value;
}

final class CloudStructuredBoolean extends CloudStructuredValue {
  const CloudStructuredBoolean(this.value);

  final bool value;
}

final class CloudStructuredNull extends CloudStructuredValue {
  const CloudStructuredNull();
}
