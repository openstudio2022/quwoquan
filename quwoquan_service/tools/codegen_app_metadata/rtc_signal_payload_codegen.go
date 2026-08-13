package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

// rtcEventsYAML mirrors rtc/rtc/call_session/events.yaml (client WS payload codegen).
type rtcEventsYAML struct {
	Events []rtcEventYAML `yaml:"events"`
}

type rtcEventYAML struct {
	Name                       string            `yaml:"name"`
	ClientWsType               string            `yaml:"client_ws_type"`
	PayloadFields              []string          `yaml:"payload_fields"`
	OptionalClientStringFields []string          `yaml:"optional_client_string_fields"`
	ClientPayloadDefaults      map[string]string `yaml:"client_payload_defaults"`
}

func rtcDartPublicFieldName(field fieldDef) string {
	if name := strings.TrimSpace(field.ClientDartName); name != "" {
		return name
	}
	return field.Name
}

func readRtcEvents(path string) (*rtcEventsYAML, error) {
	var out rtcEventsYAML
	if err := decodeMetadataDocument(path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func rtcResolveSessionField(session []fieldDef, wireName string) *fieldDef {
	for i := range session {
		f := &session[i]
		if f.Name == wireName || rtcDartPublicFieldName(*f) == wireName {
			return f
		}
	}
	return nil
}

func rtcPayloadDartScalarType(f *fieldDef) string {
	if f == nil {
		return "String"
	}
	switch f.Type {
	case "enum":
		return f.EnumRef
	case "int", "long":
		return "int"
	case "bool":
		return "bool"
	case "datetime":
		return "String"
	default:
		return "String"
	}
}

func rtcPayloadFromWireExpr(dartField, wireKey string, f *fieldDef, nullable bool, defLit string) string {
	p := fmt.Sprintf("payload['%s']", wireKey)
	if defLit != "" {
		switch {
		case f != nil && f.Type == "enum":
			return fmt.Sprintf(
				"      %s: %s == null ? %s : %s.fromWire(%s, '%s.%s'),\n",
				dartField,
				p,
				defLit,
				f.EnumRef,
				p,
				"RtcSignalPayload",
				dartField,
			)
		case f != nil && (f.Type == "int" || f.Type == "long"):
			return fmt.Sprintf("      %s: (%s as num?)?.toInt() ?? %s,\n", dartField, p, defLit)
		case f != nil && f.Type == "bool":
			return fmt.Sprintf("      %s: %s as bool? ?? %s,\n", dartField, p, defLit)
		default:
			return fmt.Sprintf("      %s: %s as String? ?? %s,\n", dartField, p, defLit)
		}
	}
	if nullable {
		switch {
		case f != nil && f.Type == "enum":
			return fmt.Sprintf(
				"      %s: %s == null ? null : %s.fromWire(%s, '%s.%s'),\n",
				dartField,
				p,
				f.EnumRef,
				p,
				"RtcSignalPayload",
				dartField,
			)
		case f != nil && (f.Type == "int" || f.Type == "long"):
			return fmt.Sprintf("      %s: (%s as num?)?.toInt(),\n", dartField, p)
		case f != nil && f.Type == "bool":
			return fmt.Sprintf("      %s: %s as bool?,\n", dartField, p)
		default:
			return fmt.Sprintf("      %s: %s as String?,\n", dartField, p)
		}
	}
	switch {
	case f != nil && f.Type == "enum":
		return fmt.Sprintf(
			"      %s: %s.fromWire(%s, '%s.%s'),\n",
			dartField,
			f.EnumRef,
			p,
			"RtcSignalPayload",
			dartField,
		)
	case f != nil && (f.Type == "int" || f.Type == "long"):
		return fmt.Sprintf("      %s: (%s as num?)?.toInt() ?? 0,\n", dartField, p)
	case f != nil && f.Type == "bool":
		return fmt.Sprintf("      %s: %s as bool? ?? false,\n", dartField, p)
	default:
		return fmt.Sprintf("      %s: %s as String? ?? '',\n", dartField, p)
	}
}

func rtcDartStringLiteral(s string) string {
	return fmt.Sprintf("'%s'", strings.ReplaceAll(s, "'", "\\'"))
}

// rtcPayloadDartIdentifier is the Dart field name for a WS payload wire key.
// Wire keys are canonical business names (`callId`, field name, or client_dart_name);
// storage `_id` is never a client WS wire key.
func rtcPayloadDartIdentifier(session []fieldDef, wireKey string) string {
	if strings.TrimSpace(wireKey) == "_id" {
		return "callId"
	}
	for i := range session {
		f := &session[i]
		if f.Name == wireKey {
			return rtcDartPublicFieldName(*f)
		}
		if rtcDartPublicFieldName(*f) == wireKey {
			return rtcDartPublicFieldName(*f)
		}
	}
	return wireKey
}

// rtcPayloadWireKey is the JSON key read from the WS payload object.
// Never emit or read storage `_id`; CallSession identity on the wire is `callId`.
func rtcPayloadWireKey(wireKey string) string {
	if strings.TrimSpace(wireKey) == "_id" {
		return "callId"
	}
	return wireKey
}

func rtcDartPayloadClassName(eventName string) string {
	return "Rtc" + eventName + "Payload"
}

func rtcDartWsPayloadClassName(eventName string) string {
	return "Rtc" + eventName + "WsPayload"
}

func rtcDartWsTypeConstName(eventName string) string {
	return "rtcWsType" + eventName
}

func emitRtcPayloadClass(b *strings.Builder, ev *rtcEventYAML, session []fieldDef) {
	class := rtcDartPayloadClassName(ev.Name)
	b.WriteString(fmt.Sprintf("/// WS payload for metadata event `%s` (`client_ws_type` = [%s]).\n", ev.Name, rtcDartWsTypeConstName(ev.Name)))
	b.WriteString(fmt.Sprintf("class %s {\n", class))
	b.WriteString(fmt.Sprintf("  const %s({\n", class))

	for _, key := range ev.PayloadFields {
		wireKey := rtcPayloadWireKey(key)
		f := rtcResolveSessionField(session, wireKey)
		if f == nil {
			f = rtcResolveSessionField(session, key)
		}
		dartID := rtcPayloadDartIdentifier(session, key)
		def := ""
		if ev.ClientPayloadDefaults != nil {
			def = strings.TrimSpace(ev.ClientPayloadDefaults[key])
			if def == "" {
				def = strings.TrimSpace(ev.ClientPayloadDefaults[wireKey])
			}
		}
		nullable := def == ""
		if nullable {
			b.WriteString(fmt.Sprintf("    this.%s,\n", dartID))
		} else {
			defLit := rtcDartStringLiteral(def)
			if f != nil && f.Type == "enum" {
				defLit = f.EnumRef + "." + toDartValueName(def)
			} else if f != nil && (f.Type == "int" || f.Type == "long") {
				defLit = def
			}
			if f != nil && f.Type == "bool" {
				defLit = def
			}
			b.WriteString(fmt.Sprintf("    this.%s = %s,\n", dartID, defLit))
		}
	}
	for _, key := range ev.OptionalClientStringFields {
		b.WriteString(fmt.Sprintf("    this.%s,\n", key))
	}
	b.WriteString("  });\n\n")

	for _, key := range ev.PayloadFields {
		wireKey := rtcPayloadWireKey(key)
		f := rtcResolveSessionField(session, wireKey)
		if f == nil {
			f = rtcResolveSessionField(session, key)
		}
		dartID := rtcPayloadDartIdentifier(session, key)
		def := ""
		if ev.ClientPayloadDefaults != nil {
			def = strings.TrimSpace(ev.ClientPayloadDefaults[key])
			if def == "" {
				def = strings.TrimSpace(ev.ClientPayloadDefaults[wireKey])
			}
		}
		nullable := def == ""
		dt := rtcPayloadDartScalarType(f)
		if nullable {
			b.WriteString(fmt.Sprintf("  final %s? %s;\n", dt, dartID))
		} else {
			b.WriteString(fmt.Sprintf("  final %s %s;\n", dt, dartID))
		}
		if f != nil {
			recordEnumFieldBinding(enumFieldBinding{
				DartClass:      class,
				DartField:      dartID,
				DartType:       dt,
				EnumRef:        f.EnumRef,
				ContractType:   f.Type,
				ContractSource: "rtc/rtc/call_session/fields.yaml",
				ClientDartType: f.ClientDartType,
			})
		}
	}
	for _, key := range ev.OptionalClientStringFields {
		b.WriteString(fmt.Sprintf("  final String? %s;\n", key))
	}

	b.WriteString(fmt.Sprintf("\n  factory %s.fromWire(Map<String, dynamic> payload) {\n", class))
	b.WriteString("    _rtcRequireExactFields(payload, const <String>{\n")
	for _, key := range ev.PayloadFields {
		b.WriteString(fmt.Sprintf("      '%s',\n", rtcPayloadWireKey(key)))
	}
	for _, key := range ev.OptionalClientStringFields {
		b.WriteString(fmt.Sprintf("      '%s',\n", key))
	}
	b.WriteString(fmt.Sprintf("    }, '%s');\n", class))
	b.WriteString(fmt.Sprintf("    return %s(\n", class))
	for _, key := range ev.PayloadFields {
		wireKey := rtcPayloadWireKey(key)
		f := rtcResolveSessionField(session, wireKey)
		if f == nil {
			f = rtcResolveSessionField(session, key)
		}
		dartID := rtcPayloadDartIdentifier(session, key)
		def := ""
		if ev.ClientPayloadDefaults != nil {
			def = strings.TrimSpace(ev.ClientPayloadDefaults[key])
			if def == "" {
				def = strings.TrimSpace(ev.ClientPayloadDefaults[wireKey])
			}
		}
		nullable := def == ""
		defLit := ""
		if def != "" {
			if f != nil && f.Type == "enum" {
				defLit = f.EnumRef + "." + toDartValueName(def)
			} else if f != nil && (f.Type == "int" || f.Type == "long") {
				defLit = def
			} else if f != nil && f.Type == "bool" {
				defLit = def
			} else {
				defLit = rtcDartStringLiteral(def)
			}
		}
		b.WriteString(rtcPayloadFromWireExpr(dartID, wireKey, f, nullable, defLit))
	}
	for _, key := range ev.OptionalClientStringFields {
		p := fmt.Sprintf("payload['%s']", key)
		b.WriteString(fmt.Sprintf("      %s: %s as String?,\n", key, p))
	}
	b.WriteString("    );\n  }\n\n")
	b.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, key := range ev.PayloadFields {
		wireKey := rtcPayloadWireKey(key)
		field := rtcResolveSessionField(session, wireKey)
		if field == nil {
			field = rtcResolveSessionField(session, key)
		}
		dartID := rtcPayloadDartIdentifier(session, key)
		def := ""
		if ev.ClientPayloadDefaults != nil {
			def = strings.TrimSpace(ev.ClientPayloadDefaults[key])
			if def == "" {
				def = strings.TrimSpace(ev.ClientPayloadDefaults[wireKey])
			}
		}
		expression := dartID
		if field != nil && field.Type == "enum" {
			expression += ".wireName"
		}
		if def == "" {
			nonNullExpression := strings.Replace(expression, dartID, dartID+"!", 1)
			b.WriteString(fmt.Sprintf("    if (%s != null) '%s': %s,\n", dartID, wireKey, nonNullExpression))
		} else {
			b.WriteString(fmt.Sprintf("    '%s': %s,\n", wireKey, expression))
		}
	}
	for _, key := range ev.OptionalClientStringFields {
		b.WriteString(fmt.Sprintf("    if (%s != null) '%s': %s,\n", key, key, key))
	}
	b.WriteString("  };\n}\n\n")
}

func emitRtcPayloadManifest(b *strings.Builder, ev *rtcEventYAML) {
	base := "rtc" + ev.Name + "PayloadWireKeys"
	b.WriteString(fmt.Sprintf("/// `%s.payload_fields`（codegen 与 events.yaml 同步）。\n", ev.Name))
	b.WriteString(fmt.Sprintf("const %s = <String>[\n", base))
	for _, key := range ev.PayloadFields {
		b.WriteString(fmt.Sprintf("  '%s',\n", rtcPayloadWireKey(key)))
	}
	b.WriteString("];\n")
	if len(ev.OptionalClientStringFields) > 0 {
		opt := "rtc" + ev.Name + "OptionalClientStringWireKeys"
		b.WriteString(fmt.Sprintf("/// `%s.optional_client_string_fields`\n", ev.Name))
		b.WriteString(fmt.Sprintf("const %s = <String>[\n", opt))
		for _, key := range ev.OptionalClientStringFields {
			b.WriteString(fmt.Sprintf("  '%s',\n", key))
		}
		b.WriteString("];\n")
	}
	b.WriteString("\n")
}

// writeRtcSignalPayloads generates WS payload DTOs + sealed [RtcWsPayload] from events.yaml.
func writeRtcSignalPayloads(appDir, metadataDir string) error {
	eventsPath := filepath.Join(metadataDir, "rtc", "rtc", "call_session", "events.yaml")
	fieldsPath := filepath.Join(metadataDir, "rtc", "rtc", "call_session", "fields.yaml")
	if !hasMetadataDocument(eventsPath) {
		return fmt.Errorf("rtc events metadata is absent")
	}
	ff, err := readFields(fieldsPath)
	if err != nil {
		return fmt.Errorf("rtc signal payloads read fields: %w", err)
	}
	ev, err := readRtcEvents(eventsPath)
	if err != nil {
		return fmt.Errorf("rtc read events: %w", err)
	}
	for i := range ev.Events {
		if strings.TrimSpace(ev.Events[i].ClientWsType) == "" {
			return fmt.Errorf("rtc events: missing client_ws_type for event %q", ev.Events[i].Name)
		}
	}
	out := renderRtcSignalPayloadsDart(metadataSourceLabel(eventsPath), ff, ev)
	outPath := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"realtime",
		"rtc_signal_payloads.g.dart",
	)
	writeFile(outPath, out)
	return nil
}

func renderRtcSignalPayloadsDart(sourcePath string, ff *fieldsFile, ev *rtcEventsYAML) string {
	session := ff.Entities["CallSession"].Fields
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from rtc/rtc/call_session/events.yaml. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")
	usedEnumRefs := map[string]bool{}
	for i := range ev.Events {
		for _, key := range ev.Events[i].PayloadFields {
			if field := rtcResolveSessionField(session, rtcPayloadWireKey(key)); field != nil && field.Type == "enum" && strings.TrimSpace(field.EnumRef) != "" {
				usedEnumRefs[field.EnumRef] = true
			}
		}
	}
	if len(usedEnumRefs) > 0 {
		refs := make([]string, 0, len(usedEnumRefs))
		for ref := range usedEnumRefs {
			refs = append(refs, ref)
		}
		sort.Strings(refs)
		b.WriteString("import '../../rtc/rtc_operation_contracts.g.dart' show ")
		b.WriteString(strings.Join(refs, ", "))
		b.WriteString(";\n\n")
	}
	b.WriteString("/// Gateway `type` string for each metadata event (`client_ws_type`).\n")
	for i := range ev.Events {
		e := &ev.Events[i]
		typ := strings.TrimSpace(e.ClientWsType)
		b.WriteString(fmt.Sprintf("/// Event `%s`\n", e.Name))
		b.WriteString(fmt.Sprintf("const %s = %s;\n\n", rtcDartWsTypeConstName(e.Name), rtcDartStringLiteral(typ)))
	}

	for i := range ev.Events {
		emitRtcPayloadClass(&b, &ev.Events[i], session)
	}

	b.WriteString("/// Sealed WS payload after parsing `payload` JSON object.\n")
	b.WriteString("sealed class RtcWsPayload {\n")
	b.WriteString("  const RtcWsPayload();\n")
	b.WriteString("  Map<String, Object?> toWire();\n")
	b.WriteString("}\n\n")

	for i := range ev.Events {
		e := &ev.Events[i]
		inner := rtcDartPayloadClassName(e.Name)
		outer := rtcDartWsPayloadClassName(e.Name)
		b.WriteString(fmt.Sprintf("final class %s extends RtcWsPayload {\n", outer))
		b.WriteString(fmt.Sprintf("  const %s(this.data);\n\n", outer))
		b.WriteString(fmt.Sprintf("  final %s data;\n", inner))
		b.WriteString("\n  @override\n")
		b.WriteString("  Map<String, Object?> toWire() => data.toWire();\n")
		b.WriteString("}\n\n")
	}

	b.WriteString("/// Parse WebSocket message body `payload` using top-level `type` (see events.yaml `client_ws_type`).\n")
	b.WriteString("RtcWsPayload parseRtcWsPayload({\n")
	b.WriteString("  required String wireType,\n")
	b.WriteString("  required Map<String, dynamic> payload,\n")
	b.WriteString("}) {\n")
	b.WriteString("  switch (wireType) {\n")
	for i := range ev.Events {
		e := &ev.Events[i]
		c := rtcDartWsTypeConstName(e.Name)
		outer := rtcDartWsPayloadClassName(e.Name)
		inner := rtcDartPayloadClassName(e.Name)
		b.WriteString(fmt.Sprintf("    case %s:\n", c))
		b.WriteString(fmt.Sprintf("      return %s(%s.fromWire(payload));\n", outer, inner))
	}
	b.WriteString("    default:\n")
	b.WriteString("      throw FormatException('Unsupported RTC realtime event type: $wireType');\n")
	b.WriteString("  }\n}\n\n")

	b.WriteString("/// All known `client_ws_type` values (codegen).\n")
	b.WriteString("const rtcWsKnownWireTypes = <String>[\n")
	for i := range ev.Events {
		b.WriteString(fmt.Sprintf("  %s,\n", rtcDartWsTypeConstName(ev.Events[i].Name)))
	}
	b.WriteString("];\n\n")
	b.WriteString("void _rtcRequireExactFields(Map<String, dynamic> payload, Set<String> allowed, String path) {\n")
	b.WriteString("  final unknown = payload.keys.where((key) => !allowed.contains(key)).toList(growable: false);\n")
	b.WriteString("  if (unknown.isNotEmpty) { throw FormatException('$path contains unknown fields: ${unknown.join(',')}'); }\n")
	b.WriteString("}\n\n")

	for i := range ev.Events {
		emitRtcPayloadManifest(&b, &ev.Events[i])
	}

	return b.String()
}
