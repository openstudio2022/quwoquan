package main

import (
	"fmt"
	"strings"
)

// 字段关系渲染只支持本观察版本；authoring结构变化必须显式更新验证器，不能静默漏校验。
func validateObservationContract(launch appLaunchMetadata) error {
	s := launch.Schemas.RehearsalStorageObservation
	if s.SchemaValue != "rehearsal-storage-observation" {
		return fmt.Errorf("observation schema discriminator invalid")
	}
	if err := requireExactStringSet("observation fields", s.RequiredFields, []string{"schema", "status", "configurationState", "startupAttemptId", "generation", "bindingDigest", "consumers"}); err != nil {
		return err
	}
	if err := requireExactOrderedStrings("observation status", s.Fields["status"].AllowedValues, []string{"available", "unavailable"}); err != nil {
		return err
	}
	if err := requireExactOrderedStrings("configuration states", s.Fields["configurationState"].AllowedValues, []string{"not_observed", "verified", "invalidated"}); err != nil {
		return err
	}
	c := s.Fields["consumers"]
	if err := requireExactStringSet("consumer names", c.RequiredFields, []string{"auth", "installId", "pending", "rehearsal"}); err != nil {
		return err
	}
	for _, name := range c.RequiredFields {
		f := c.Fields[name]
		if err := requireExactStringSet("consumer fields", f.RequiredFields, []string{"state", "namespaceDigest", "successfulOperations"}); err != nil {
			return err
		}
		if err := requireExactOrderedStrings("consumer states", f.Fields["state"].AllowedValues, []string{"not_observed", "constructed", "io_observed", "invalidated"}); err != nil {
			return err
		}
		operations := f.Fields["successfulOperations"]
		if operations.Items == nil {
			return fmt.Errorf("observation operations missing")
		}
		if err := requireExactOrderedStrings("successful operations", operations.Items.AllowedValues, []string{"read", "write", "delete"}); err != nil {
			return err
		}
		if f.Fields["namespaceDigest"].Format != "optional_sha256_identity" {
			return fmt.Errorf("namespace digest format invalid")
		}
	}
	var r struct {
		Channel        string `yaml:"channel"`
		Method         string `yaml:"method"`
		Classification string `yaml:"classification"`
		LogPolicy      string `yaml:"log_policy"`
		ResponseSchema string `yaml:"response_schema"`
	}
	if err := launch.RehearsalStorageReadback.Decode(&r); err != nil {
		return err
	}
	if r.Channel != "quwoquan/startup/timings" || r.Method != "readRehearsalStorageObservation" || r.Classification != "INTERNAL" || r.LogPolicy != "drop" || r.ResponseSchema != "rehearsal_storage_observation" {
		return fmt.Errorf("observation readback/privacy contract invalid")
	}
	return nil
}

func observationMember(value string) string {
	parts := strings.Split(value, "_")
	for i := 1; i < len(parts); i++ {
		parts[i] = strings.ToUpper(parts[i][:1]) + parts[i][1:]
	}
	return strings.Join(parts, "")
}

func observationReadback(contract appLaunchContract) map[string]any {
	return contract.NormalizedAppLaunchManifest["rehearsal_storage_readback"].(map[string]any)
}

func renderObservationPython(contract appLaunchContract) string {
	readback := observationReadback(contract)
	return fmt.Sprintf(`
REHEARSAL_STORAGE_OBSERVATION_CHANNEL = %q
REHEARSAL_STORAGE_OBSERVATION_METHOD = %q

def validate_rehearsal_storage_observation(value):
    """纯验证当前观察，不执行I/O、不签发隔离或授权结论。"""
    import re
    schema = APP_LAUNCH_MANIFEST["schemas"]["rehearsal_storage_observation"]
    def shape(v, field):
        kind = field["type"]
        if kind == "object":
            if not isinstance(v, dict) or set(v) != set(field["required_fields"]):
                raise ValueError("invalid observation fields")
            for key, child in field["fields"].items(): shape(v[key], child)
        elif kind == "array":
            if not isinstance(v, list): raise ValueError("invalid observation array")
            for item in v: shape(item, field["items"])
            if len(set(v)) != len(v): raise ValueError("duplicate observation operation")
        elif kind == "string":
            if not isinstance(v, str): raise ValueError("invalid observation string")
            if "const" in field and v != field["const"]: raise ValueError("invalid observation schema")
            if "allowed_values" in field and v not in field["allowed_values"]: raise ValueError("invalid observation state")
            if field.get("format") == "optional_sha256_identity" and v and not re.fullmatch(r"sha256:[a-f0-9]{64}", v):
                raise ValueError("invalid observation digest")
        else: raise ValueError("unsupported observation field")
    shape(value, {"type":"object", **schema})
    available = value["status"] == "available"
    config = value["configurationState"]
    if available:
        if config != "verified" or not value["bindingDigest"] or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["startupAttemptId"]) or not re.fullmatch(r"[1-9][0-9]{0,15}", value["generation"]):
            raise ValueError("invalid observation identity")
    elif any(value[k] for k in ("bindingDigest","startupAttemptId","generation")):
        raise ValueError("unavailable observation retains identity")
    for consumer in value["consumers"].values():
        state, digest, operations = consumer["state"], consumer["namespaceDigest"], consumer["successfulOperations"]
        if state in ("constructed","io_observed"):
            if not available or not digest or ((state == "io_observed") != bool(operations)):
                raise ValueError("invalid observation IO state")
        elif digest or operations: raise ValueError("inactive observation retains facts")
        if config in ("not_observed","invalidated") and state != config:
            raise ValueError("configuration consumer state mismatch")
    return None
`, readback["channel"], readback["method"])
}

func renderObservationDart(contract appLaunchContract) string {
	r := observationReadback(contract)
	schema := contract.NormalizedAppLaunchManifest["schemas"].(map[string]any)["rehearsal_storage_observation"].(map[string]any)
	fields := schema["fields"].(map[string]any)
	consumers := fields["consumers"].(map[string]any)
	consumer := consumers["fields"].(map[string]any)["auth"].(map[string]any)
	child := consumer["fields"].(map[string]any)
	var out strings.Builder
	fmt.Fprintf(&out, "\nconst String rehearsalStorageObservationChannel = %q;\nconst String rehearsalStorageObservationMethod = %q;\n", r["channel"], r["method"])
	for _, e := range []struct {
		name   string
		values any
	}{
		{"RehearsalObservationStatus", fields["status"].(map[string]any)["allowed_values"]},
		{"RehearsalConfigurationObservationState", fields["configurationState"].(map[string]any)["allowed_values"]},
		{"RehearsalConsumerObservationState", child["state"].(map[string]any)["allowed_values"]},
		{"RehearsalSuccessfulOperation", child["successfulOperations"].(map[string]any)["items"].(map[string]any)["allowed_values"]},
	} {
		fmt.Fprintf(&out, "enum %s {\n", e.name)
		for _, v := range e.values.([]any) {
			fmt.Fprintf(&out, "  %s(%q),\n", observationMember(v.(string)), v)
		}
		fmt.Fprintf(&out, "  ; const %s(this.wireName); final String wireName;\n}\n", e.name)
	}
	out.WriteString(`
T _observationEnum<T extends Enum>(Object? value, List<T> values, String Function(T) wire) {
  for (final member in values) { if (value == wire(member)) return member; }
  throw const FormatException('Invalid observation enum');
}
Map<String, Object?> _observationObject(Object? value, Set<String> fields) {
  if (value is! Map || value.length != fields.length || !value.keys.every(fields.contains)) {
    throw const FormatException('Invalid observation fields');
  }
  return Map<String, Object?>.from(value);
}
String _observationString(Object? value) {
  if (value is! String) throw const FormatException('Invalid observation string');
  return value;
}
String _observationDigest(Object? value) {
  final text = _observationString(value);
  if (text.isNotEmpty && RegExp(r'^sha256:[a-f0-9]{64}$').matchAsPrefix(text)?.end != text.length) {
    throw const FormatException('Invalid observation digest');
  }
  return text;
}
final class RehearsalConsumerObservation {
  const RehearsalConsumerObservation._(this.state, this.namespaceDigest, this.successfulOperations);
  final RehearsalConsumerObservationState state;
  final String namespaceDigest;
  final List<RehearsalSuccessfulOperation> successfulOperations;
  factory RehearsalConsumerObservation.fromWire(Object? input) {
    final value = _observationObject(input, const {'state','namespaceDigest','successfulOperations'});
    final state = _observationEnum(value['state'], RehearsalConsumerObservationState.values, (v) => v.wireName);
    final digest = _observationDigest(value['namespaceDigest']);
    final raw = value['successfulOperations'];
    if (raw is! List) throw const FormatException('Invalid observation operations');
    final operations = raw.map((v) => _observationEnum(v, RehearsalSuccessfulOperation.values, (o) => o.wireName)).toList();
    if (operations.toSet().length != operations.length) throw const FormatException('Duplicate observation operation');
    final live = state == RehearsalConsumerObservationState.constructed || state == RehearsalConsumerObservationState.ioObserved;
    if (live ? (digest.isEmpty || ((state == RehearsalConsumerObservationState.ioObserved) != operations.isNotEmpty)) : (digest.isNotEmpty || operations.isNotEmpty)) {
      throw const FormatException('Invalid consumer observation relation');
    }
    return RehearsalConsumerObservation._(state, digest, List.unmodifiable(operations));
  }
  Map<String,Object?> toWire() => {'state':state.wireName,'namespaceDigest':namespaceDigest,'successfulOperations':successfulOperations.map((v)=>v.wireName).toList()};
}
final class RehearsalStorageObservation {
  const RehearsalStorageObservation._(this.status,this.configurationState,this.startupAttemptId,this.generation,this.bindingDigest,this.auth,this.installId,this.pending,this.rehearsal);
  final RehearsalObservationStatus status;
  final RehearsalConfigurationObservationState configurationState;
  final String startupAttemptId;
  final String generation;
  final String bindingDigest;
  final RehearsalConsumerObservation auth, installId, pending, rehearsal;
  factory RehearsalStorageObservation.fromWire(Object? input) {
    final value = _observationObject(input,const {'schema','status','configurationState','startupAttemptId','generation','bindingDigest','consumers'});
    if(value['schema'] != 'rehearsal-storage-observation') throw const FormatException('Invalid observation schema');
    final status=_observationEnum(value['status'],RehearsalObservationStatus.values,(v)=>v.wireName);
    final config=_observationEnum(value['configurationState'],RehearsalConfigurationObservationState.values,(v)=>v.wireName);
    final attempt=_observationString(value['startupAttemptId']);
    final generation=_observationString(value['generation']);
    final digest=_observationDigest(value['bindingDigest']);
    final available=status==RehearsalObservationStatus.available;
    if(available ? (config!=RehearsalConfigurationObservationState.verified || digest.isEmpty || attempt.isEmpty || RegExp(r'^[A-Za-z0-9_-]{1,128}$').matchAsPrefix(attempt)?.end != attempt.length || generation.isEmpty || RegExp(r'^[1-9][0-9]{0,15}$').matchAsPrefix(generation)?.end != generation.length) : (attempt.isNotEmpty || generation.isNotEmpty || digest.isNotEmpty)) {
      throw const FormatException('Invalid observation identity');
    }
    final raw=_observationObject(value['consumers'],const {'auth','installId','pending','rehearsal'});
    final consumers=raw.map((key,v)=>MapEntry(key,RehearsalConsumerObservation.fromWire(v)));
    for(final c in consumers.values) {
      if(!available && (c.state==RehearsalConsumerObservationState.constructed || c.state==RehearsalConsumerObservationState.ioObserved)) throw const FormatException('Unavailable observation has consumer facts');
      if(config!=RehearsalConfigurationObservationState.verified && c.state.wireName!=config.wireName) throw const FormatException('Configuration consumer mismatch');
    }
    return RehearsalStorageObservation._(status,config,attempt,generation,digest,consumers['auth']!,consumers['installId']!,consumers['pending']!,consumers['rehearsal']!);
  }
  Map<String,Object?> toWire()=>{'schema':'rehearsal-storage-observation','status':status.wireName,'configurationState':configurationState.wireName,'startupAttemptId':startupAttemptId,'generation':generation,'bindingDigest':bindingDigest,'consumers':{'auth':auth.toWire(),'installId':installId.toWire(),'pending':pending.toWire(),'rehearsal':rehearsal.toWire()}};
}
`)
	return out.String()
}
