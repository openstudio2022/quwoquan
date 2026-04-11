package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRtcCallSessionDtoGeneration_containsAllEntityFieldNames(t *testing.T) {
	root := filepath.Join("..", "..", "contracts", "metadata", "rtc", "call_session", "fields.yaml")
	ff, err := readFields(root)
	if err != nil {
		t.Fatalf("read fields: %v", err)
	}
	out := renderRtcCallSessionDtosDartFromFields(root, ff)

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
	ff, err := readFields(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	got := strings.TrimSpace(renderRtcCallSessionDtosDartFromFields(path, ff))
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
