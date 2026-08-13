// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
// readiness_case: execute-persisted-graphql-query-local
package local_contract

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"strings"
	"testing"

	registryinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/registry"
)

func TestEd25519RegistryVerifierAcceptsOnlyConfiguredExactKeyAndSignature(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := registryinfra.NewEd25519SignatureVerifier(map[string]string{
		"release-signing-2026": base64.StdEncoding.EncodeToString(publicKey),
	})
	if err != nil {
		t.Fatal(err)
	}
	// candidateDigest value is sha256("release-bound").
	payload := []byte(`{"candidateDigest":"sha256:dbc45d65eca68258b9ab5de200273eb3730784a1694123bd68b6c623748158d6"}`)
	signature := ed25519.Sign(privateKey, payload)
	if err := verifier.Verify(
		context.Background(), "release-signing-2026", payload, signature,
	); err != nil {
		t.Fatalf("valid signature rejected: %v", err)
	}

	mutated := append([]byte(nil), payload...)
	mutated[len(mutated)-2] ^= 1
	if err := verifier.Verify(
		context.Background(), "release-signing-2026", mutated, signature,
	); err == nil {
		t.Fatal("mutated payload must fail verification")
	}
	if err := verifier.Verify(
		context.Background(), "unknown-key", payload, signature,
	); err == nil {
		t.Fatal("unknown keyId must fail closed")
	}
	if err := verifier.Verify(
		context.Background(), "release-signing-2026", payload, signature[:16],
	); err == nil {
		t.Fatal("non-Ed25519 signature length must fail closed")
	}
}

func TestEd25519RegistryVerifierRejectsInvalidConfiguration(t *testing.T) {
	publicKey, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	validKey := base64.StdEncoding.EncodeToString(publicKey)
	for _, testCase := range []struct {
		name string
		keys map[string]string
	}{
		{name: "empty set", keys: nil},
		{name: "blank key id", keys: map[string]string{"": validKey}},
		{name: "whitespace key id", keys: map[string]string{" release": validKey}},
		{name: "oversized key id", keys: map[string]string{strings.Repeat("k", 129): validKey}},
		{name: "non canonical base64", keys: map[string]string{"release": validKey + "\n"}},
		{name: "wrong key length", keys: map[string]string{
			"release": base64.StdEncoding.EncodeToString(publicKey[:16]),
		}},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			if _, err := registryinfra.NewEd25519SignatureVerifier(testCase.keys); err == nil {
				t.Fatal("invalid public key configuration must fail at startup")
			}
		})
	}
}
