package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestDartTypeBindsEnumSeparatesTypedFromBareString(t *testing.T) {
	cases := []struct {
		dartType string
		enumRef  string
		want     bool
	}{
		{"Visibility", "Visibility", true},
		{"Visibility?", "Visibility", true},
		{"List<Visibility>", "Visibility", true},
		{"List<Visibility>?", "Visibility", true},
		{"Set<Visibility>?", "Visibility", true},
		{"String", "Visibility", false},
		{"String?", "Visibility", false},
		{"List<String>", "Visibility", false},
		{"CircleVisibility", "Visibility", false},
		{"", "Visibility", false},
		{"Visibility", "", false},
	}
	for _, testCase := range cases {
		got := dartTypeBindsEnum(testCase.dartType, testCase.enumRef)
		if got != testCase.want {
			t.Fatalf(
				"dartTypeBindsEnum(%q, %q) = %v, want %v",
				testCase.dartType,
				testCase.enumRef,
				got,
				testCase.want,
			)
		}
	}
}

func TestRecordEnumFieldBindingIgnoresFieldsWithoutEnumRef(t *testing.T) {
	resetEnumFieldBindings()
	t.Cleanup(resetEnumFieldBindings)

	recordEnumFieldBinding(enumFieldBinding{
		DartClass: "PostProjection",
		DartField: "postId",
		DartType:  "String",
	})
	if len(pendingEnumFieldBindings) != 0 {
		t.Fatalf("a field without enum_ref carries no typed-binding obligation")
	}

	recordEnumFieldBinding(enumFieldBinding{
		DartClass: "PostProjection",
		DartField: "visibility",
		DartType:  "String",
		EnumRef:   "Visibility",
	})
	if len(pendingEnumFieldBindings) != 1 {
		t.Fatalf("enum-bound field was not recorded")
	}
	if pendingEnumFieldBindings[0].Typed {
		t.Fatalf("a bare String bound to Visibility must be reported as untyped")
	}
}

// A renderer that recorded bindings and never reached writeFile must not have
// them silently misattributed to whichever file is written next.
func TestUnattachedBindingsStayInTheReportWithoutAPath(t *testing.T) {
	resetEnumFieldBindings()
	t.Cleanup(resetEnumFieldBindings)

	recordEnumFieldBinding(enumFieldBinding{
		DartClass: "Orphan",
		DartField: "state",
		DartType:  "String",
		EnumRef:   "SubjectFollowState",
	})

	path := filepath.Join(t.TempDir(), "report.json")
	if err := writeFieldBindingReport(path); err != nil {
		t.Fatalf("write report: %v", err)
	}
	var report fieldBindingReport
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	if err := json.Unmarshal(data, &report); err != nil {
		t.Fatalf("decode report: %v", err)
	}
	if len(report.Bindings) != 1 {
		t.Fatalf("expected the orphan binding to survive, got %d", len(report.Bindings))
	}
	if report.Bindings[0].GeneratedPath != "" {
		t.Fatalf(
			"an unattached binding must not claim a generated path, got %q",
			report.Bindings[0].GeneratedPath,
		)
	}
}

func TestFieldBindingReportIsSortedAndDeduplicated(t *testing.T) {
	resetEnumFieldBindings()
	t.Cleanup(resetEnumFieldBindings)

	enumFieldBindings = []enumFieldBinding{
		{GeneratedPath: "b.dart", DartClass: "B", DartField: "x", EnumRef: "E"},
		{GeneratedPath: "a.dart", DartClass: "A", DartField: "z", EnumRef: "E"},
		{GeneratedPath: "a.dart", DartClass: "A", DartField: "y", EnumRef: "E"},
		{GeneratedPath: "a.dart", DartClass: "A", DartField: "y", EnumRef: "E"},
	}

	path := filepath.Join(t.TempDir(), "report.json")
	if err := writeFieldBindingReport(path); err != nil {
		t.Fatalf("write report: %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	var report fieldBindingReport
	if err := json.Unmarshal(data, &report); err != nil {
		t.Fatalf("decode report: %v", err)
	}
	want := []string{"a.dart/A.y", "a.dart/A.z", "b.dart/B.x"}
	if len(report.Bindings) != len(want) {
		t.Fatalf("expected %d bindings, got %d", len(want), len(report.Bindings))
	}
	for index, expected := range want {
		binding := report.Bindings[index]
		actual := binding.GeneratedPath + "/" + binding.DartClass + "." + binding.DartField
		if actual != expected {
			t.Fatalf("binding %d = %s, want %s", index, actual, expected)
		}
	}
}

// The committed report is what the enum typed-binding gate reads. If codegen
// ever stops emitting it, the gate must not silently pass on an empty scan.
func TestCommittedFieldBindingReportCoversTheGeneratedContracts(t *testing.T) {
	path := filepath.Join(
		repoRootForFieldBindingTest(t),
		"quwoquan_app/tool/cloud_codegen/field_binding_report.json",
	)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read committed report: %v", err)
	}
	var report fieldBindingReport
	if err := json.Unmarshal(data, &report); err != nil {
		t.Fatalf("decode committed report: %v", err)
	}
	if len(report.Bindings) == 0 {
		t.Fatalf("committed report has no bindings; codegen stopped emitting them")
	}
	paths := map[string]struct{}{}
	for _, binding := range report.Bindings {
		if binding.EnumRef == "" {
			t.Fatalf("report contains a binding without enum_ref: %+v", binding)
		}
		if binding.GeneratedPath == "" {
			t.Fatalf("report contains an unattached binding: %+v", binding)
		}
		paths[binding.GeneratedPath] = struct{}{}
	}
	// Domain operation contracts, generated requests and the assistant wire
	// tree are the three renderers that historically produced untyped enum
	// fields; losing any of them would blind the gate.
	for _, required := range []string{
		"packages/quwoquan_cloud_contracts/lib/src/content/content_operation_contracts.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/content/content_operation_contracts.g.requests.g.dart",
		"packages/quwoquan_cloud_contracts/lib/src/generated/assistant/assistant_api_responses.g.dart",
	} {
		if _, covered := paths[required]; !covered {
			t.Fatalf("report no longer covers %s", required)
		}
	}
}

func repoRootForFieldBindingTest(t *testing.T) string {
	t.Helper()
	directory, err := os.Getwd()
	if err != nil {
		t.Fatalf("resolve working directory: %v", err)
	}
	// `quwoquan_service/quwoquan_app/` exists as a stray empty directory, so the
	// root has to be identified by two sibling trees rather than one name.
	for {
		_, appErr := os.Stat(filepath.Join(directory, "quwoquan_app", "pubspec.yaml"))
		_, serviceErr := os.Stat(filepath.Join(directory, "quwoquan_service", "go.mod"))
		if appErr == nil && serviceErr == nil {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Fatalf("cannot locate repository root")
		}
		directory = parent
	}
}
