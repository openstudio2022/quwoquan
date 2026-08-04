package main

import (
	"fmt"
	"path"
	"path/filepath"
	"sort"
	"strings"
)

const realtimeEventCatalogPath = "_shared/realtime_event_catalog.yaml"

type realtimeEventCatalog struct {
	Events []realtimeEventCatalogEntry `yaml:"events"`
}

type realtimeEventCatalogEntry struct {
	WireType      string `yaml:"wire_type"`
	Owner         string `yaml:"owner"`
	EventRef      string `yaml:"event_ref"`
	PayloadEntity string `yaml:"payload_entity"`
}

type realtimeCatalogEventSource struct {
	Name          string `yaml:"name"`
	ClientWsType  string `yaml:"client_ws_type"`
	PayloadEntity string `yaml:"payload_entity"`
}

type realtimeCatalogEventsDocument struct {
	Events []realtimeCatalogEventSource `yaml:"events"`
}

type realtimeCatalogProjectionDocument struct {
	RealtimeContract string `yaml:"realtime_contract"`
	ClientWsType     string `yaml:"client_ws_type"`
	PayloadEntity    string `yaml:"payload_entity"`
	ClientCodegen    struct {
		EnvelopeClass string `yaml:"envelope_class"`
	} `yaml:"client_codegen"`
}

func loadRealtimeEventCatalog() (realtimeEventCatalog, error) {
	if activeMetadataSource == nil {
		return realtimeEventCatalog{}, fmt.Errorf("ContractGraph is not initialized")
	}
	if !activeMetadataSource.Has(realtimeEventCatalogPath) {
		return realtimeEventCatalog{}, fmt.Errorf("canonical realtime event catalog is missing")
	}
	var catalog realtimeEventCatalog
	if err := activeMetadataSource.Decode(realtimeEventCatalogPath, &catalog); err != nil {
		return realtimeEventCatalog{}, fmt.Errorf("decode %s: %w", realtimeEventCatalogPath, err)
	}
	return catalog, nil
}

func validateRealtimeEventCatalog(catalog realtimeEventCatalog) error {
	if len(catalog.Events) == 0 {
		return fmt.Errorf("realtime event catalog must not be empty")
	}
	objects := map[string]string{}
	for _, object := range activeMetadataSource.Graph().Objects {
		objects[object.ID] = path.Dir(filepath.ToSlash(object.SourcePath))
	}
	seenWire := map[string]string{}
	seenRef := map[string]struct{}{}
	registeredSource := map[string]struct{}{}
	for _, entry := range catalog.Events {
		entry.WireType = strings.TrimSpace(entry.WireType)
		entry.Owner = strings.TrimSpace(entry.Owner)
		entry.EventRef = strings.TrimSpace(entry.EventRef)
		entry.PayloadEntity = strings.TrimSpace(entry.PayloadEntity)
		if entry.WireType == "" || entry.Owner == "" || entry.EventRef == "" || entry.PayloadEntity == "" {
			return fmt.Errorf("realtime catalog entries require wire_type, owner, event_ref and payload_entity")
		}
		if previous, duplicate := seenWire[entry.WireType]; duplicate {
			return fmt.Errorf("realtime wire_type %s has multiple owners: %s and %s", entry.WireType, previous, entry.Owner)
		}
		if _, duplicate := seenRef[entry.EventRef]; duplicate {
			return fmt.Errorf("realtime event_ref %s is duplicated", entry.EventRef)
		}
		seenWire[entry.WireType] = entry.Owner
		seenRef[entry.EventRef] = struct{}{}
		objectDir, exists := objects[entry.Owner]
		if !exists {
			return fmt.Errorf("realtime event %s references unknown owner %s", entry.WireType, entry.Owner)
		}
		if !strings.HasPrefix(entry.EventRef, entry.Owner+".") {
			return fmt.Errorf("realtime event_ref %s is not owned by %s", entry.EventRef, entry.Owner)
		}
		localName := strings.TrimPrefix(entry.EventRef, entry.Owner+".")
		matched, err := validateRealtimeCatalogSource(objectDir, localName, entry)
		if err != nil {
			return err
		}
		if !matched {
			return fmt.Errorf("realtime event_ref %s has no canonical object-local event or realtime_contract", entry.EventRef)
		}
		registeredSource[objectDir+"\x00"+localName] = struct{}{}
	}

	// Every source that explicitly declares a client wire type must enter the
	// one catalog. This is the fail-closed edge that prevents a producer from
	// silently creating a second WS/LongPoll decoder path.
	for _, sourcePath := range activeMetadataSource.Paths("", ".yaml") {
		if strings.HasSuffix(sourcePath, "/events.yaml") {
			var document realtimeCatalogEventsDocument
			if err := activeMetadataSource.Decode(sourcePath, &document); err != nil {
				return fmt.Errorf("decode realtime source %s: %w", sourcePath, err)
			}
			objectDir := path.Dir(sourcePath)
			for _, event := range document.Events {
				if strings.TrimSpace(event.ClientWsType) == "" {
					continue
				}
				if _, ok := registeredSource[objectDir+"\x00"+strings.TrimSpace(event.Name)]; !ok {
					return fmt.Errorf("client realtime event %s#%s is missing from %s", sourcePath, event.Name, realtimeEventCatalogPath)
				}
			}
		}
		if strings.Contains(sourcePath, "/projections/") {
			var projection realtimeCatalogProjectionDocument
			if err := activeMetadataSource.Decode(sourcePath, &projection); err != nil {
				return fmt.Errorf("decode realtime projection %s: %w", sourcePath, err)
			}
			if strings.TrimSpace(projection.ClientWsType) == "" {
				continue
			}
			objectDir := path.Dir(path.Dir(sourcePath))
			if _, ok := registeredSource[objectDir+"\x00"+strings.TrimSpace(projection.RealtimeContract)]; !ok {
				return fmt.Errorf("client realtime contract %s#%s is missing from %s", sourcePath, projection.RealtimeContract, realtimeEventCatalogPath)
			}
		}
	}
	return nil
}

func validateRealtimeCatalogSource(
	objectDir string,
	localName string,
	entry realtimeEventCatalogEntry,
) (bool, error) {
	eventsPath := path.Join(objectDir, "events.yaml")
	if activeMetadataSource.Has(eventsPath) {
		var document realtimeCatalogEventsDocument
		if err := activeMetadataSource.Decode(eventsPath, &document); err != nil {
			return false, fmt.Errorf("decode %s: %w", eventsPath, err)
		}
		for _, event := range document.Events {
			if strings.TrimSpace(event.Name) != localName {
				continue
			}
			if strings.TrimSpace(event.ClientWsType) != entry.WireType {
				return false, fmt.Errorf("%s client_ws_type=%q, catalog=%q", entry.EventRef, event.ClientWsType, entry.WireType)
			}
			if strings.TrimSpace(event.PayloadEntity) != entry.PayloadEntity {
				return false, fmt.Errorf("%s payload_entity=%q, catalog=%q", entry.EventRef, event.PayloadEntity, entry.PayloadEntity)
			}
			fields, err := readFields(path.Join(objectDir, "fields.yaml"))
			if err != nil {
				return false, fmt.Errorf("read fields for %s: %w", entry.EventRef, err)
			}
			if _, exists := fields.Types[entry.PayloadEntity]; !exists {
				if _, exists = fields.Entities[entry.PayloadEntity]; !exists {
					if _, exists = fields.ValueObjects[entry.PayloadEntity]; !exists {
						return false, fmt.Errorf("%s payload_entity %s is not object-local", entry.EventRef, entry.PayloadEntity)
					}
				}
			}
			return true, nil
		}
	}
	for _, projectionPath := range activeMetadataSource.Paths(path.Join(objectDir, "projections"), ".yaml") {
		var projection realtimeCatalogProjectionDocument
		if err := activeMetadataSource.Decode(projectionPath, &projection); err != nil {
			return false, fmt.Errorf("decode %s: %w", projectionPath, err)
		}
		if strings.TrimSpace(projection.RealtimeContract) != localName {
			continue
		}
		if strings.TrimSpace(projection.ClientWsType) != entry.WireType ||
			strings.TrimSpace(projection.PayloadEntity) != entry.PayloadEntity ||
			strings.TrimSpace(projection.ClientCodegen.EnvelopeClass) != entry.PayloadEntity {
			return false, fmt.Errorf("%s realtime_contract metadata does not match catalog", entry.EventRef)
		}
		return true, nil
	}
	return false, nil
}

func renderRealtimeEventCatalogDart(catalog realtimeEventCatalog) (string, error) {
	if err := validateRealtimeEventCatalog(catalog); err != nil {
		return "", err
	}
	events := append([]realtimeEventCatalogEntry{}, catalog.Events...)
	sort.Slice(events, func(i, j int) bool { return events[i].WireType < events[j].WireType })
	var output strings.Builder
	output.WriteString("// Code generated from _shared/realtime_event_catalog.yaml. DO NOT EDIT.\n")
	output.WriteString("// Payload fields remain owned by object-local contracts.\n\n")
	output.WriteString("import 'chat_realtime_events.g.dart';\n")
	output.WriteString("import 'feed_realtime_patch.g.dart';\n")
	output.WriteString("import 'rtc_signal_payloads.g.dart';\n\n")
	output.WriteString("export 'chat_realtime_events.g.dart';\n")
	output.WriteString("export 'feed_realtime_patch.g.dart';\n")
	output.WriteString("export 'rtc_signal_payloads.g.dart';\n")
	output.WriteString("export 'shared_realtime_event_enums.g.dart';\n\n")
	output.WriteString("sealed class RealtimeEventEnvelope {\n")
	output.WriteString("  const RealtimeEventEnvelope({required this.wireType, this.eventId, required this.occurredAt});\n")
	output.WriteString("  factory RealtimeEventEnvelope.fromWire(Map<String, Object?> wire, [String path = 'RealtimeEventEnvelope']) => decodeRealtimeEventEnvelope(wire, path);\n")
	output.WriteString("  final String wireType;\n  final String? eventId;\n  final DateTime occurredAt;\n  Map<String, Object?> toWire();\n}\n\n")
	output.WriteString("final class ChatRealtimeEventEnvelope extends RealtimeEventEnvelope {\n")
	output.WriteString("  const ChatRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});\n")
	output.WriteString("  final ChatRealtimeEventPayload payload;\n  @override\n  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());\n}\n\n")
	output.WriteString("final class RtcRealtimeEventEnvelope extends RealtimeEventEnvelope {\n")
	output.WriteString("  const RtcRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});\n")
	output.WriteString("  final RtcWsPayload payload;\n  @override\n  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());\n}\n\n")
	output.WriteString("final class UserSyncHintEventPayload {\n")
	output.WriteString("  const UserSyncHintEventPayload({required this.userId, required this.latestSyncSeq});\n")
	output.WriteString("  final String userId;\n  final int latestSyncSeq;\n")
	output.WriteString("  Map<String, Object?> toWire() => <String, Object?>{'userId': userId, 'latestSyncSeq': latestSyncSeq};\n}\n\n")
	output.WriteString("final class UserSyncHintRealtimeEventEnvelope extends RealtimeEventEnvelope {\n")
	output.WriteString("  const UserSyncHintRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});\n")
	output.WriteString("  final UserSyncHintEventPayload payload;\n  @override\n  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());\n}\n\n")
	output.WriteString("final class FeedPatchRealtimeEventEnvelope extends RealtimeEventEnvelope {\n")
	output.WriteString("  const FeedPatchRealtimeEventEnvelope({required super.wireType, super.eventId, required super.occurredAt, required this.payload});\n")
	output.WriteString("  final FeedRealtimePatch payload;\n  @override\n  Map<String, Object?> toWire() => _realtimeEnvelopeToWire(wireType, eventId, occurredAt, payload.toWire());\n}\n\n")
	output.WriteString("const realtimeEventOwnerByWireType = <String, String>{\n")
	for _, event := range events {
		output.WriteString(fmt.Sprintf("  '%s': '%s',\n", strings.ReplaceAll(event.WireType, "'", "\\'"), event.Owner))
	}
	output.WriteString("};\n\n")
	output.WriteString("String requireRealtimeEventOwner(String wireType) {\n")
	output.WriteString("  final owner = realtimeEventOwnerByWireType[wireType];\n")
	output.WriteString("  if (owner == null) { throw FormatException('Unsupported realtime event type: $wireType'); }\n")
	output.WriteString("  return owner;\n}\n")
	output.WriteString(`

RealtimeEventEnvelope decodeRealtimeEventEnvelope(Map<String, Object?> wire, [String path = 'RealtimeEventEnvelope']) {
  _realtimeRequireExactFields(wire, const <String>{'type', 'eventId', 'occurredAt', 'payload'}, path);
  final wireType = _realtimeRequiredString(wire, 'type', '$path.type');
  requireRealtimeEventOwner(wireType);
  final eventId = _realtimeOptionalString(wire, 'eventId', '$path.eventId');
  final occurredAtRaw = _realtimeRequiredString(wire, 'occurredAt', '$path.occurredAt');
  final occurredAt = DateTime.tryParse(occurredAtRaw);
  if (occurredAt == null) throw FormatException('$path.occurredAt must be ISO-8601');
  final rawPayload = wire['payload'];
  if (rawPayload is! Map || rawPayload.keys.any((key) => key is! String)) throw FormatException('$path.payload must be an object');
  final payload = Map<String, dynamic>.from(rawPayload);
  switch (wireType) {
`)
	for _, event := range events {
		wireType := strings.ReplaceAll(event.WireType, "'", "\\'")
		output.WriteString(fmt.Sprintf("    case '%s':\n", wireType))
		switch {
		case strings.HasPrefix(event.Owner, "chat."):
			output.WriteString("      return ChatRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: decodeChatRealtimeEventPayload(eventType: wireType, payload: payload));\n")
		case strings.HasPrefix(event.Owner, "rtc."):
			output.WriteString("      return RtcRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseRtcWsPayload(wireType: wireType, payload: payload));\n")
		case event.WireType == "sync_hint":
			output.WriteString("      _realtimeRequireExactFields(payload, const <String>{'userId', 'latestSyncSeq'}, 'UserSyncHintEventPayload');\n")
			output.WriteString("      final userId = _realtimeRequiredString(payload, 'userId', 'UserSyncHintEventPayload.userId');\n")
			output.WriteString("      final latestSyncSeq = payload['latestSyncSeq'];\n")
			output.WriteString("      if (latestSyncSeq is! int || latestSyncSeq <= 0) throw FormatException('UserSyncHintEventPayload.latestSyncSeq must be positive integer');\n")
			output.WriteString("      return UserSyncHintRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: UserSyncHintEventPayload(userId: userId, latestSyncSeq: latestSyncSeq));\n")
		case event.WireType == "feed.patch":
			output.WriteString("      return FeedPatchRealtimeEventEnvelope(wireType: wireType, eventId: eventId, occurredAt: occurredAt, payload: parseFeedRealtimePatch(payload));\n")
		default:
			return "", fmt.Errorf("realtime catalog owner %s has no generated decoder", event.Owner)
		}
	}
	output.WriteString(`    default:
      throw FormatException('Unsupported realtime event type: $wireType');
  }
}

Map<String, Object?> _realtimeEnvelopeToWire(
  String wireType,
  String? eventId,
  DateTime occurredAt,
  Map<String, Object?> payload,
) => <String, Object?>{
  'type': wireType,
  if (eventId != null) 'eventId': eventId,
  'occurredAt': occurredAt.toUtc().toIso8601String(),
  'payload': payload,
};

void _realtimeRequireExactFields(Map<String, Object?> wire, Set<String> allowed, String path) {
  final unknown = wire.keys.where((key) => !allowed.contains(key)).toList(growable: false);
  if (unknown.isNotEmpty) throw FormatException('$path contains unknown fields: ${unknown.join(',')}');
}

String _realtimeRequiredString(Map<String, Object?> wire, String field, String path) {
  final value = wire[field];
  if (value is! String || value.trim().isEmpty) throw FormatException('$path must be a non-empty string');
  return value.trim();
}

String? _realtimeOptionalString(Map<String, Object?> wire, String field, String path) {
  final value = wire[field];
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) throw FormatException('$path must be a non-empty string');
  return value.trim();
}
`)
	return output.String(), nil
}

func writeRealtimeEventCatalog(appDir string) error {
	catalog, err := loadRealtimeEventCatalog()
	if err != nil {
		return err
	}
	output, err := renderRealtimeEventCatalogDart(catalog)
	if err != nil {
		return err
	}
	writeFile(filepath.Join(
		appDir,
		"packages", "quwoquan_cloud_contracts", "lib", "src", "generated", "realtime", "realtime_event_catalog.g.dart",
	), output)
	return nil
}
