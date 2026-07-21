package main

import (
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
)

func TestMaterializeReleaseBindingsDisablesBlockedExternalInteractions(t *testing.T) {
	cfg := config{Environment: "gamma"}
	cfg.Integration.ExternalInteraction.SMS.Enabled = true
	cfg.Integration.ExternalInteraction.Push.Enabled = true

	resolved, err := materializeReleaseExternalInteractionBindings(
		cfg,
		runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
	)
	if err != nil {
		t.Fatalf("blocked capabilities must not prevent unrelated service startup: %v", err)
	}
	if resolved.Integration.ExternalInteraction.SMS.Enabled {
		t.Fatal("blocked SMS capability must not be materialized")
	}
	if resolved.Integration.ExternalInteraction.Push.Enabled {
		t.Fatal("blocked push capability must not be materialized")
	}
}
