package runtimeconfig

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"

	configrelease "quwoquan_service/runtime/configrelease"
)

// DefaultClusterName derives the control-plane cluster identity from the
// canonical application environment.
func DefaultClusterName(appEnv string) string {
	switch appEnv {
	case "beta":
		return "beta-control-a"
	case "gamma":
		return "gamma-control-a"
	case "prod":
		return "prod-control-a"
	default:
		return appEnv + "-control-a"
	}
}

// LoadCanonicalSnapshot loads the single rendered runtime snapshot selected
// by configrelease. It never falls back to repository environment definitions.
func LoadCanonicalSnapshot(
	serviceName string,
	appEnv string,
	configRoot string,
	target any,
) error {
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read generated runtime config: %w", err)
	}
	if err := yaml.Unmarshal(raw, target); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}
