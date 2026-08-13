package servicehost

import "testing"

const (
	standaloneConfigDigest = "sha256:5b565a33b80b75dc462328a68cb5b57d31e3fe1a246438e70629059fcb8aca19" // sha256("standalone")
	fallbackConfigDigest   = "sha256:5c7ee2074b65853f71fc5a01ce194ff26deedf6daacdb715c6beefdfd3f31b35" // sha256("fallback")
	userConfigDigest       = "sha256:04f8996da763b7a969b1028ee3007569eaf3a635486ddab211d512c85b9df8fb" // sha256("user")
)

func TestModuleEnvironmentValuePreservesStandaloneContract(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "")
	t.Setenv("SERVICE_NAME", "standalone-name")
	t.Setenv("CONFIG_VERSION", standaloneConfigDigest)

	if got := ModuleEnvironmentValue("user-service", "SERVICE_NAME"); got != "standalone-name" {
		t.Fatalf("standalone service name = %q, want standalone-name", got)
	}
	if got := ModuleEnvironmentValue("user-service", "CONFIG_VERSION"); got != standaloneConfigDigest {
		t.Fatalf("standalone config version = %q, want %q", got, standaloneConfigDigest)
	}
}

func TestModuleEnvironmentValueUsesServiceCoreScope(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "1")
	t.Setenv("SERVICE_NAME", "drifted")
	t.Setenv("CONFIG_VERSION", fallbackConfigDigest)
	t.Setenv("SERVICE_CORE_USER_SERVICE_CONFIG_VERSION", userConfigDigest)

	if got := ModuleEnvironmentValue("user-service", "SERVICE_NAME"); got != "user-service" {
		t.Fatalf("service-core service name = %q, want user-service", got)
	}
	if got := ModuleEnvironmentValue("user-service", "CONFIG_VERSION"); got != userConfigDigest {
		t.Fatalf("service-core config version = %q, want %q", got, userConfigDigest)
	}
	if got := ModuleEnvironmentValue("chat-service", "CONFIG_VERSION"); got != fallbackConfigDigest {
		t.Fatalf("service-core fallback = %q, want %q", got, fallbackConfigDigest)
	}
}
