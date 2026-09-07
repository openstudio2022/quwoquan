package main

import (
	"context"
	"os"
	"testing"
)

func TestRunFailsClosedWithoutDeploymentAdminEnvironment(t *testing.T) {
	previous := os.Args
	os.Args = []string{"product-ops-elasticsearch-bootstrap"}
	t.Cleanup(func() { os.Args = previous })

	err := run(context.Background(), func(string) (string, bool) { return "", false })
	if err == nil || err.Error() != endpointEnv+" is required" {
		t.Fatalf("run() error = %v", err)
	}
}

func TestRequiredEnvironmentRejectsBlankValue(t *testing.T) {
	_, err := requiredEnvironment(func(key string) (string, bool) {
		return "  ", key == apiKeyEnv
	}, apiKeyEnv)
	if err == nil || err.Error() != apiKeyEnv+" is required" {
		t.Fatalf("requiredEnvironment() error = %v", err)
	}
}
