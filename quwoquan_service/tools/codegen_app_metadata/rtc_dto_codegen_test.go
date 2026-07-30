package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRtcCallSessionDtoGeneration_containsAllEntityFieldNames(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	root := filepath.Join(metadataDir, "rtc", "rtc", "call_session", "fields.yaml")
	ff, err := readFields(root)
	if err != nil {
		t.Fatalf("read fields: %v", err)
	}
	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		t.Fatalf("read shared enum catalog: %v", err)
	}
	out := renderRtcCallSessionDtosDartFromFields(root, ff, shared.Enums)

	cp := ff.Entities["CallParticipant"].Fields
	for _, f := range cp {
		name := rtcDartPublicFieldName(f)
		if !strings.Contains(out, name) {
			t.Errorf("generated dart missing CallParticipant field %q", name)
		}
	}

	cs := ff.Entities["CallSession"].Fields
	for _, f := range cs {
		name := rtcDartPublicFieldName(f)
		if !strings.Contains(out, name) {
			t.Errorf("generated dart missing CallSession field %q", name)
		}
	}
}

func TestRtcCallSessionDtoGeneration_Golden(t *testing.T) {
	path := filepath.Join("testdata", "rtc_fields_min.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var ff fieldsFile
	err = yaml.Unmarshal(data, &ff)
	if err != nil {
		t.Fatalf("parse fixture: %v", err)
	}
	got := strings.TrimSpace(renderRtcCallSessionDtosDartFromFields(
		path,
		&ff,
		map[string][]string{
			"CallStatus": {"initiated", "ringing", "connecting", "in_call", "ended"},
		},
	))
	wantPath := filepath.Join("testdata", "rtc_call_session_dtos.want.dart")

	if os.Getenv("UPDATE_RTC_GOLDEN") == "1" {
		if err := os.WriteFile(wantPath, []byte(got+"\n"), 0o644); err != nil {
			t.Fatalf("write golden: %v", err)
		}
		t.Logf("wrote %s", wantPath)
		return
	}

	wantBytes, err := os.ReadFile(wantPath)
	if err != nil {
		t.Fatalf("read golden: %v (set UPDATE_RTC_GOLDEN=1 to create)", err)
	}
	want := strings.TrimSpace(string(wantBytes))
	if got != want {
		t.Fatalf("golden mismatch: run with UPDATE_RTC_GOLDEN=1 after intentional emitter changes\ngot len=%d want len=%d", len(got), len(want))
	}
}

func TestRtcCallSessionDtoGeneration_UsesStrictSharedEnums(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"CallParticipant": {Fields: []fieldDef{{
			Name: "role", Type: "enum", EnumRef: "ParticipantRole",
			Constraints: []string{"NOT_NULL"}, ClientDefault: "invitee",
		}}},
		"CallSession": {Fields: []fieldDef{
			{Name: "callId", Type: "string", Constraints: []string{"PK"}},
			{Name: "endReason", Type: "enum", EnumRef: "EndReason", Constraints: []string{"NULLABLE"}},
		}},
	}}
	out := renderRtcCallSessionDtosDartFromFields(
		"rtc/rtc/call_session/fields.yaml",
		fields,
		map[string][]string{
			"ParticipantRole": {"initiator", "invitee"},
			"EndReason":       {"normal", "no_answer", "account_closed"},
		},
	)
	for _, required := range []string{
		"enum EndReason",
		"noAnswer('no_answer')",
		"accountClosed('account_closed')",
		"throw FormatException('Unknown EndReason wire value: $raw')",
		"final EndReason? endReason;",
		"EndReason.fromString(_rtcRequiredString(map, 'endReason'))",
		"endReason!.toApiString()",
		"callId: _rtcRequiredString(map, 'callId')",
		"throw FormatException('RTC field \"$key\" must be a non-empty string')",
	} {
		if !strings.Contains(out, required) {
			t.Fatalf("typed RTC enum output misses %q", required)
		}
	}
	for _, forbidden := range []string{"final String? endReason;", "unknown,"} {
		if strings.Contains(out, forbidden) {
			t.Fatalf("typed RTC enum output keeps legacy fallback %q", forbidden)
		}
	}
}

func TestRtcCallSessionDtoGeneration_UsesCanonicalOwnedListType(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"CallParticipant": {Fields: []fieldDef{{
			Name: "userId", Type: "string", Constraints: []string{"NOT_NULL"},
		}}},
		"CallSession": {Fields: []fieldDef{
			{Name: "callId", Type: "string", Constraints: []string{"PK"}},
			{Name: "participants", Type: "[]CallParticipant", Constraints: []string{"NULLABLE"}},
		}},
	}}
	out := renderRtcCallSessionDtosDartFromFields(
		"rtc/rtc/call_session/fields.yaml",
		fields,
		nil,
	)
	for _, required := range []string{
		"this.participants = const []",
		"final List<CallParticipantDto> participants;",
		"participants.add(CallParticipantDto.fromMap(p))",
		"'participants': participants.map((p) => p.toMap()).toList()",
	} {
		if !strings.Contains(out, required) {
			t.Fatalf("canonical RTC owned-list output misses %q", required)
		}
	}
	for _, forbidden := range []string{
		"final String participants;",
		"participants: _rtcRequiredString",
	} {
		if strings.Contains(out, forbidden) {
			t.Fatalf("canonical RTC owned-list output contains scalar fallback %q", forbidden)
		}
	}
}

func TestRtcCallSessionDtoGeneration_RequiresCanonicalIdentityName(t *testing.T) {
	defer func() {
		if recovered := recover(); recovered == nil {
			t.Fatal("expected storage _id without client_dart_name to fail")
		}
	}()

	rtcToJsonKey(fieldDef{Name: "_id", Source: "_id", Type: "ObjectId"})
}
