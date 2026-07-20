package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestAssistantWireEntityOrderSortsDependenciesDeterministically(t *testing.T) {
	names := []string{"Aggregate", "Beta", "Gamma"}
	dependencies := map[string]map[string]bool{
		"Aggregate": {
			"Gamma": true,
			"Beta":  true,
		},
		"Beta":  {},
		"Gamma": {},
	}
	want := []string{"Beta", "Gamma", "Aggregate"}

	for attempt := 0; attempt < 100; attempt++ {
		got := assistantWireTopoEntityOrder(names, dependencies)
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("attempt %d order = %v, want %v", attempt, got, want)
		}
	}
}

func TestAssistantPreferenceMetadataGeneratesTypedWire(t *testing.T) {
	appDir := t.TempDir()
	metadataDir := initializeTestContractGraph(t)
	if err := generateAssistantCloudApiWireDart(metadataDir, appDir); err != nil {
		t.Fatalf("generateAssistantCloudApiWireDart() error = %v", err)
	}
	outputPath := filepath.Join(
		appDir,
		"lib",
		"cloud",
		"runtime",
		"generated",
		"assistant",
		"assistant_cloud_api_wire.g.dart",
	)
	payload, err := os.ReadFile(outputPath)
	if err != nil {
		t.Fatalf("read generated assistant wire: %v", err)
	}
	output := string(payload)
	for _, required := range []string{
		"class AssistantPreferenceFact {",
		"class AssistantPreferenceFactListView {",
		"final List<AssistantPreferenceFact> items;",
	} {
		if !strings.Contains(output, required) {
			t.Fatalf("generated assistant wire missing %q", required)
		}
	}
}
