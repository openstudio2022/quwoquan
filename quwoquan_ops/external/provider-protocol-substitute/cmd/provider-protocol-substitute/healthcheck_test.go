package main

import (
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestRunTLSHealthcheckUsesTheDeclaredCAAndRejectsNonReadyResponses(t *testing.T) {
	status := http.StatusOK
	server := httptest.NewTLSServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(status)
	}))
	defer server.Close()
	caFile := filepath.Join(t.TempDir(), "ca.crt")
	certificate := server.Certificate()
	if certificate == nil {
		t.Fatal("TLS test server did not expose its certificate")
	}
	if err := os.WriteFile(caFile, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certificate.Raw}), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := runTLSHealthcheck(server.URL, caFile); err != nil {
		t.Fatalf("trusted healthy endpoint was rejected: %v", err)
	}
	status = http.StatusServiceUnavailable
	if err := runTLSHealthcheck(server.URL, caFile); err == nil {
		t.Fatal("non-ready endpoint must fail the healthcheck")
	}
}

func TestRunTLSHealthcheckRejectsAnUntrustedEndpoint(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer server.Close()
	caFile := filepath.Join(t.TempDir(), "ca.crt")
	if err := os.WriteFile(caFile, []byte("not a certificate"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := runTLSHealthcheck(server.URL, caFile); err == nil {
		t.Fatal("invalid CA must fail the healthcheck")
	}
}
