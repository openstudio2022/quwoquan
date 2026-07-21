package main

import (
	"context"
	"reflect"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

func TestParseCommandOptionsUsesManifestRefsByDefault(t *testing.T) {
	env := map[string]string{
		"APP_ENV":                      "beta",
		"RETIRED_ASSISTANT_SEED_INPUT": "retired_value_must_be_ignored",
	}
	options, err := parseCommandOptions(nil, func(key string) string { return env[key] })
	if err != nil {
		t.Fatalf("parseCommandOptions() error = %v", err)
	}
	if options.Environment != "beta" {
		t.Fatalf("environment=%q, want beta", options.Environment)
	}
	if len(options.Refs) != 0 {
		t.Fatalf("refs=%v, want manifest-owned empty override", options.Refs)
	}
	if options.Timeout != 90*time.Second {
		t.Fatalf("timeout=%s, want 90s", options.Timeout)
	}
}

func TestParseCommandOptionsConsumesOnlyAssistantSeedRefs(t *testing.T) {
	env := map[string]string{
		"APP_ENV":             "gamma",
		"ASSISTANT_SEED_REFS": "assistant_p0_core, skill_management_core,assistant_p0_core",
	}
	options, err := parseCommandOptions(nil, func(key string) string { return env[key] })
	if err != nil {
		t.Fatalf("parseCommandOptions() error = %v", err)
	}
	want := []string{"assistant_p0_core", "skill_management_core"}
	if !reflect.DeepEqual(options.Refs, want) {
		t.Fatalf("refs=%v, want %v", options.Refs, want)
	}
}

func TestParseCommandOptionsRejectsAlphaAndProd(t *testing.T) {
	for _, env := range []string{"alpha", "prod"} {
		t.Run(env, func(t *testing.T) {
			_, err := parseCommandOptions(
				[]string{"--env", env},
				func(string) string { return "" },
			)
			if err == nil {
				t.Fatalf("--env %s should be rejected", env)
			}
		})
	}
}

func TestParseCommandOptionsRejectsInvalidTimeout(t *testing.T) {
	_, err := parseCommandOptions(
		[]string{"--env", "beta", "--timeout-seconds", "0"},
		func(string) string { return "" },
	)
	if err == nil {
		t.Fatal("zero timeout should be rejected")
	}
}

func TestRequireAssistantSeedMessageTransportUsesSeedDescriptor(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })

	transport, err := requireAssistantSeedMessageTransport(
		context.Background(),
		"alpha",
		router,
		map[string]string{"general": "memory"},
	)
	if err != nil {
		t.Fatalf("alpha seed fixture transport error = %v", err)
	}
	if transport == nil {
		t.Fatal("alpha seed fixture transport is nil")
	}
	if _, err := requireAssistantSeedMessageTransport(
		context.Background(),
		"beta",
		router,
		map[string]string{"general": "memory"},
	); err == nil {
		t.Fatal("beta seed memory transport must fail closed")
	}
}
