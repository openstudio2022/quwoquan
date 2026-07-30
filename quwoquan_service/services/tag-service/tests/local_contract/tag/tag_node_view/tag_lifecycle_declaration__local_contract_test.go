package local_contract

import (
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/lifecycle"
)

func TestOmittedLifecycleDeclarationImportsAsActiveWithoutWindow(t *testing.T) {
	status, window, err := lifecycle.ResolveDeclaration("", nil)
	if err != nil {
		t.Fatal(err)
	}
	if status != lifecycle.StatusActive {
		t.Fatalf("status = %q, want active", status)
	}
	if window != nil {
		t.Fatalf("window = %#v, want nil", window)
	}
}

func TestSeasonalDeclarationKeepsItsWindowInUTC(t *testing.T) {
	status, window, err := lifecycle.ResolveDeclaration("seasonal", &lifecycle.WindowDeclaration{
		StartAt:    "2026-03-01T00:00:00+08:00",
		EndAt:      "2026-05-31T23:59:59+08:00",
		Recurrence: "annual",
	})
	if err != nil {
		t.Fatal(err)
	}
	if status != lifecycle.StatusSeasonal {
		t.Fatalf("status = %q, want seasonal", status)
	}
	if window == nil {
		t.Fatal("seasonal declaration lost its window")
	}
	if got, want := window.StartAt.Format(time.RFC3339), "2026-02-28T16:00:00Z"; got != want {
		t.Fatalf("startAt = %s, want %s", got, want)
	}
	if window.Recurrence != lifecycle.RecurrenceAnnual {
		t.Fatalf("recurrence = %q, want annual", window.Recurrence)
	}
}

func TestWindowedStatusWithoutWindowIsRejected(t *testing.T) {
	for _, status := range []string{"seasonal", "campaign"} {
		_, _, err := lifecycle.ResolveDeclaration(status, nil)
		if err == nil {
			t.Fatalf("lifecycleStatus %s without a window must fail the import", status)
		}
		if !strings.Contains(err.Error(), "requires heatWindow") {
			t.Fatalf("error = %v, want a requires-heatWindow diagnosis", err)
		}
	}
}

func TestEvergreenStatusWithWindowIsRejected(t *testing.T) {
	window := &lifecycle.WindowDeclaration{
		StartAt:    "2026-03-01T00:00:00Z",
		EndAt:      "2026-05-31T00:00:00Z",
		Recurrence: "annual",
	}
	for _, status := range []string{"", "active", "trending", "deprecated"} {
		if _, _, err := lifecycle.ResolveDeclaration(status, window); err == nil {
			t.Fatalf("lifecycleStatus %q must not carry a heat window", status)
		}
	}
}

func TestMalformedWindowFailsInsteadOfDecodingToZeroTime(t *testing.T) {
	cases := map[string]*lifecycle.WindowDeclaration{
		"empty startAt": {StartAt: "", EndAt: "2026-05-31T00:00:00Z", Recurrence: "annual"},
		"date only":     {StartAt: "2026-03-01", EndAt: "2026-05-31T00:00:00Z", Recurrence: "annual"},
		"end before start": {
			StartAt: "2026-05-31T00:00:00Z", EndAt: "2026-03-01T00:00:00Z", Recurrence: "annual",
		},
		"equal bounds": {
			StartAt: "2026-03-01T00:00:00Z", EndAt: "2026-03-01T00:00:00Z", Recurrence: "annual",
		},
		"unknown recurrence": {
			StartAt: "2026-03-01T00:00:00Z", EndAt: "2026-05-31T00:00:00Z", Recurrence: "monthly",
		},
	}
	for name, declared := range cases {
		if _, _, err := lifecycle.ResolveDeclaration("seasonal", declared); err == nil {
			t.Fatalf("%s must be rejected", name)
		}
	}
}

func TestUnknownLifecycleStatusFailsTheImport(t *testing.T) {
	if _, _, err := lifecycle.ResolveDeclaration("retired", nil); err == nil {
		t.Fatal("an unknown lifecycleStatus must fail the import")
	}
}

func TestCanonicalWindowSeparatesOtherwiseIdenticalNodes(t *testing.T) {
	_, annual, err := lifecycle.ResolveDeclaration("seasonal", &lifecycle.WindowDeclaration{
		StartAt: "2026-03-01T00:00:00Z", EndAt: "2026-05-31T00:00:00Z", Recurrence: "annual",
	})
	if err != nil {
		t.Fatal(err)
	}
	_, once, err := lifecycle.ResolveDeclaration("campaign", &lifecycle.WindowDeclaration{
		StartAt: "2026-03-01T00:00:00Z", EndAt: "2026-05-31T00:00:00Z", Recurrence: "once",
	})
	if err != nil {
		t.Fatal(err)
	}
	if lifecycle.CanonicalWindow(annual) == lifecycle.CanonicalWindow(once) {
		t.Fatal("release digest must change when only the recurrence changes")
	}
	if lifecycle.CanonicalWindow(nil) != "" {
		t.Fatal("an absent window must hash as empty")
	}
	if lifecycle.SameWindow(annual, once) {
		t.Fatal("SameWindow must separate different recurrences")
	}
	if !lifecycle.SameWindow(nil, nil) {
		t.Fatal("two absent windows are the same window")
	}
	if lifecycle.SameWindow(annual, nil) {
		t.Fatal("a window and no window are not the same window")
	}
}
