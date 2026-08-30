package main

import (
	"context"
	"errors"
	"os"
	"reflect"
	"testing"

	"quwoquan_service/runtime/servicehost"
)

func TestCanonicalCompositionHasStableModulesAndEndpoints(t *testing.T) {
	t.Parallel()

	factories, endpoints, err := canonicalCompositionInputs()
	if err != nil {
		t.Fatalf("canonicalCompositionInputs() error = %v", err)
	}
	if len(factories) != 11 {
		t.Fatalf("factory count = %d, want 11", len(factories))
	}
	if len(endpoints) != len(factories) {
		t.Fatalf("endpoint count = %d, want %d", len(endpoints), len(factories))
	}
	names := make([]string, 0, len(factories))
	for index, factory := range factories {
		names = append(names, factory.Name)
		if endpoints[index].Module != factory.Name {
			t.Fatalf(
				"endpoint[%d].Module = %q, want %q",
				index,
				endpoints[index].Module,
				factory.Name,
			)
		}
	}
	want := []string{
		"user-service",
		"integration-service",
		"notification-service",
		"entity-service",
		"tag-service",
		"search-service",
		"content-service",
		"circle-service",
		"chat-service",
		"assistant-service",
		"api-edge",
	}
	if !reflect.DeepEqual(names, want) {
		t.Fatalf("module order = %v, want %v", names, want)
	}
	composition, err := servicehost.NewCompositionWithEndpoints(
		compositionProfile,
		endpoints,
		factories...,
	)
	if err != nil {
		t.Fatalf("NewCompositionWithEndpoints() error = %v", err)
	}
	const wantDigest = "sha256:9d0c452d38f17f89c509a0036c4f76197a9ba82a9151138cac85de292ce2c918"
	if got := composition.Identity().CompositionDigest; got != wantDigest {
		t.Fatalf("CompositionDigest = %q, want %q", got, wantDigest)
	}
}

func TestPrepareVirtualHTTPRoutingOverridesStandaloneAddress(t *testing.T) {
	t.Setenv("USER_SERVICE_ADDR", ":18081")
	t.Setenv(entityAccountSecurityAuthorityBaseURLEnvKey, "")

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		t.Fatalf("prepareVirtualHTTPRouting() error = %v", err)
	}
	defer router.Shutdown(t.Context())
	if got := os.Getenv("USER_SERVICE_ADDR"); got != "127.0.0.1:28081" {
		t.Fatalf("USER_SERVICE_ADDR = %q, want hidden listener", got)
	}
	if got := os.Getenv(entityAccountSecurityAuthorityBaseURLEnvKey); got != "http://127.0.0.1:28081" {
		t.Fatalf(
			"%s = %q, want service-core user authority",
			entityAccountSecurityAuthorityBaseURLEnvKey,
			got,
		)
	}
}

func TestPrepareVirtualHTTPRoutingSealsHiddenListeners(t *testing.T) {
	for _, key := range []string{
		"USER_SERVICE_ADDR",
		"CHAT_SERVICE_ADDR",
		"ASSISTANT_SERVICE_ADDR",
		"NOTIFICATION_SERVICE_ADDR",
	} {
		t.Setenv(key, "")
	}

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		t.Fatalf("prepareVirtualHTTPRouting() error = %v", err)
	}
	if router == nil {
		t.Fatal("prepareVirtualHTTPRouting() router = nil")
	}
	if got := os.Getenv("USER_SERVICE_ADDR"); got != "127.0.0.1:28081" {
		t.Fatalf("USER_SERVICE_ADDR = %q, want hidden listener", got)
	}
}

type preflightTestModule struct {
	name      string
	validated bool
	migrated  bool
	bound     bool
}

func (module *preflightTestModule) Name() string         { return module.name }
func (module *preflightTestModule) ConfigDigest() string { return "sha256:test" }
func (module *preflightTestModule) ValidateConfig(context.Context) error {
	module.validated = true
	return nil
}
func (module *preflightTestModule) PrepareMigration(context.Context) error {
	if !module.validated {
		return errors.New("migration ran before validation")
	}
	module.migrated = true
	return nil
}
func (module *preflightTestModule) Bind(context.Context) error {
	module.bound = true
	return errors.New("preflight must not bind")
}
func (module *preflightTestModule) Start(context.Context) error         { return nil }
func (module *preflightTestModule) Ready(context.Context) error         { return nil }
func (module *preflightTestModule) OpenAdmission(context.Context) error { return nil }
func (module *preflightTestModule) Shutdown(context.Context) error      { return nil }

func TestRunPreflightValidatesAndMigratesWithoutBindingListeners(t *testing.T) {
	module := &preflightTestModule{name: "assistant-service"}
	composition, err := servicehost.NewComposition(
		"service-core-preflight",
		servicehost.ModuleFactory{
			Name: module.name,
			New:  func() (servicehost.Module, error) { return module, nil },
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := runPreflight(composition); err != nil {
		t.Fatalf("runPreflight() error = %v", err)
	}
	if !module.validated || !module.migrated {
		t.Fatalf("preflight did not validate and migrate: %#v", module)
	}
	if module.bound {
		t.Fatal("preflight bound a listener")
	}
}

func TestApplyModuleEnvironmentScopesSharedProcessConfiguration(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "1")
	t.Setenv("SERVICE_NAME", "service-core")
	t.Setenv("CONFIG_VERSION", "sha256:aggregate")
	t.Setenv(
		"SERVICE_CORE_SEARCH_SERVICE_CONFIG_VERSION",
		"sha256:search",
	)
	t.Setenv(
		"SERVICE_CORE_SEARCH_SERVICE_SERVICE_INSTANCE_ID",
		"search-service-core-1",
	)

	restore, err := applyModuleEnvironment("search-service")
	if err != nil {
		t.Fatalf("applyModuleEnvironment() error = %v", err)
	}
	if got := os.Getenv("SERVICE_NAME"); got != "search-service" {
		t.Fatalf("SERVICE_NAME = %q, want search-service", got)
	}
	if got := os.Getenv("CONFIG_VERSION"); got != "sha256:search" {
		t.Fatalf("CONFIG_VERSION = %q, want search digest", got)
	}
	if got := os.Getenv("SERVICE_INSTANCE_ID"); got != "search-service-core-1" {
		t.Fatalf("SERVICE_INSTANCE_ID = %q, want module instance", got)
	}
	restore()
	if got := os.Getenv("SERVICE_NAME"); got != "service-core" {
		t.Fatalf("restored SERVICE_NAME = %q, want service-core", got)
	}
	if got := os.Getenv("CONFIG_VERSION"); got != "sha256:aggregate" {
		t.Fatalf("restored CONFIG_VERSION = %q, want aggregate digest", got)
	}
}

func TestApplyModuleEnvironmentFailsWithoutModuleConfig(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "1")
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("SERVICE_CORE_SEARCH_SERVICE_CONFIG_VERSION", "")

	if _, err := applyModuleEnvironment("search-service"); err == nil {
		t.Fatal("applyModuleEnvironment() error = nil, want missing config error")
	}
}
