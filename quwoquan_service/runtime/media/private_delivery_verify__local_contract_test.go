// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
package runtimemedia

import (
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// privateDeliverySignatureCases mirrors the shared parity vectors consumed by
// the Python local_media_origin adapter test. Both sides assert every case,
// so a one-sided verifier change fails in local_contract.
type privateDeliverySignatureCases struct {
	Schema              string   `json:"schema"`
	SignKey             string   `json:"signKey"`
	NowUnix             int64    `json:"nowUnix"`
	PrivatePathPrefixes []string `json:"privatePathPrefixes"`
	Cases               []struct {
		Name      string `json:"name"`
		Path      string `json:"path"`
		Expires   int64  `json:"expires"`
		Sign      string `json:"sign"`
		WantValid bool   `json:"wantValid"`
	} `json:"cases"`
}

func loadPrivateDeliverySignatureCases(t *testing.T) privateDeliverySignatureCases {
	t.Helper()
	path := filepath.Join(
		"..", "..", "..",
		"quwoquan_service", "services", "content-service",
		"contracts", "media", "media_asset",
		"private_delivery_signature_cases.json",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("shared private delivery signature cases are unreadable: %v", err)
	}
	var document privateDeliverySignatureCases
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatalf("shared private delivery signature cases are invalid JSON: %v", err)
	}
	if document.Schema != "content_media_private_delivery_signature_cases" {
		t.Fatalf("unexpected shared case schema: %q", document.Schema)
	}
	if len(document.Cases) == 0 {
		t.Fatal("shared private delivery signature cases must not be empty")
	}
	return document
}

func TestPrivateDeliverySignatureMatchesSharedCases(t *testing.T) {
	document := loadPrivateDeliverySignatureCases(t)
	now := time.Unix(document.NowUnix, 0).UTC()
	for _, testCase := range document.Cases {
		t.Run(testCase.Name, func(t *testing.T) {
			got := VerifyPrivateDeliverySignature(
				testCase.Path,
				testCase.Sign,
				fmt.Sprintf("%d", testCase.Expires),
				document.SignKey,
				now,
			)
			if got != testCase.WantValid {
				t.Fatalf(
					"verify(%q, t=%d) = %v, want %v",
					testCase.Path, testCase.Expires, got, testCase.WantValid,
				)
			}
		})
	}
}

func TestSharedPrivatePathPrefixesAreTheSingleClosedSet(t *testing.T) {
	document := loadPrivateDeliverySignatureCases(t)
	if len(document.PrivatePathPrefixes) != len(PrivateDeliveryPathPrefixes) {
		t.Fatalf(
			"private prefix closed set drift: shared=%v go=%v",
			document.PrivatePathPrefixes, PrivateDeliveryPathPrefixes,
		)
	}
	for index, prefix := range PrivateDeliveryPathPrefixes {
		if document.PrivatePathPrefixes[index] != prefix {
			t.Fatalf(
				"private prefix closed set drift: shared=%v go=%v",
				document.PrivatePathPrefixes, PrivateDeliveryPathPrefixes,
			)
		}
	}
	for _, testCase := range document.Cases {
		if !IsPrivateDeliveryPath(testCase.Path) {
			t.Fatalf("shared case path escapes the private closed set: %q", testCase.Path)
		}
	}
}

func TestSignedURLRoundTripsThroughEdgeVerification(t *testing.T) {
	const signKey = "round-trip-sign-key"
	now := time.Unix(1767225600, 0).UTC()
	objectKey := "media/objects/sha256/aa/bb/" + strings.Repeat("a", 64) + ".jpg"
	signed := SignCDNURLUntil(
		"https://media-cdn.local",
		objectKey,
		signKey,
		now.Add(10*time.Minute),
	)
	if signed == "" {
		t.Fatal("signer refused a canonical private object key")
	}
	parsed, err := url.Parse(signed)
	if err != nil {
		t.Fatalf("signed URL is unparseable: %v", err)
	}
	query := parsed.Query()
	if !VerifyPrivateDeliverySignature(
		parsed.EscapedPath(),
		query.Get("sign"),
		query.Get("t"),
		signKey,
		now,
	) {
		t.Fatal("issuer-signed URL must verify at the delivery edge")
	}
	// 换 key 即失效：edge 与签发方必须消费同一 secret reference。
	if VerifyPrivateDeliverySignature(
		parsed.EscapedPath(),
		query.Get("sign"),
		query.Get("t"),
		"another-key",
		now,
	) {
		t.Fatal("a foreign sign key must not verify")
	}
	// 过期即拒绝，即使签名真实。
	if VerifyPrivateDeliverySignature(
		parsed.EscapedPath(),
		query.Get("sign"),
		query.Get("t"),
		signKey,
		now.Add(11*time.Minute),
	) {
		t.Fatal("an expired grant must not verify")
	}
}
