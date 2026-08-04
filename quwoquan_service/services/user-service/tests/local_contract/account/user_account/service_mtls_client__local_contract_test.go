package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestNewIntegrationServiceMTLSClientRejectsEmptyCA(t *testing.T) {
	dir := t.TempDir()
	caPath := filepath.Join(dir, "ca.crt")
	certPath := filepath.Join(dir, "client.crt")
	keyPath := filepath.Join(dir, "client.key")
	if err := os.WriteFile(caPath, []byte{}, 0o600); err != nil {
		t.Fatalf("write empty CA: %v", err)
	}
	if err := os.WriteFile(certPath, []byte("not-a-cert"), 0o600); err != nil {
		t.Fatalf("write cert: %v", err)
	}
	if err := os.WriteFile(keyPath, []byte("not-a-key"), 0o600); err != nil {
		t.Fatalf("write key: %v", err)
	}

	t.Setenv("INTEGRATION_SERVICE_MTLS_CA_FILE", caPath)
	t.Setenv("INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE", certPath)
	t.Setenv("INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE", keyPath)

	_, err := userintegration.NewIntegrationServiceMTLSClient(0)
	if err == nil {
		t.Fatal("expected empty CA to fail closed")
	}
	if got := err.Error(); got != "integration service mTLS CA contains no certificate" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestNewIntegrationServiceMTLSClientRequiresEnvPaths(t *testing.T) {
	t.Setenv("INTEGRATION_SERVICE_MTLS_CA_FILE", "")
	t.Setenv("INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE", "")
	t.Setenv("INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE", "")

	_, err := userintegration.NewIntegrationServiceMTLSClient(0)
	if err == nil {
		t.Fatal("expected missing mTLS env to fail closed")
	}
	if got := err.Error(); got != "INTEGRATION_SERVICE_MTLS_CA_FILE is required for integration service mTLS" {
		t.Fatalf("unexpected error: %v", err)
	}
}
