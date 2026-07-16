package otpseal

import (
	"bytes"
	"encoding/base64"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestDecodeCanonicalRawURLRejectsEquivalentEncodingAlias(t *testing.T) {
	const alias = "AR"
	canonical := base64.RawURLEncoding.EncodeToString([]byte{0x01})
	if canonical != "AQ" {
		t.Fatalf("unexpected canonical vector %q", canonical)
	}
	decodedAlias, err := base64.RawURLEncoding.DecodeString(alias)
	if err != nil || !bytes.Equal(decodedAlias, []byte{0x01}) {
		t.Fatalf("test vector must be a byte-equivalent alias: decoded=%x err=%v", decodedAlias, err)
	}
	if _, err := decodeCanonicalRawURL(alias); !errors.Is(err, ErrInvalidReference) {
		t.Fatalf("non-canonical alias must be rejected, got %v", err)
	}
	decodedCanonical, err := decodeCanonicalRawURL(canonical)
	if err != nil || !bytes.Equal(decodedCanonical, []byte{0x01}) {
		t.Fatalf("canonical value must be accepted: decoded=%x err=%v", decodedCanonical, err)
	}
}

func TestOtpCodeSealerRoundTripAndRejectsTamperBindingExpiryAndUnknownKey(t *testing.T) {
	now := time.Date(2026, 7, 15, 12, 0, 0, 0, time.UTC)
	encodedKey := base64.StdEncoding.EncodeToString([]byte("0123456789abcdef0123456789abcdef"))
	sealer, err := NewFromBase64("k1", map[string]string{"k1": encodedKey})
	if err != nil {
		t.Fatal(err)
	}
	sealer.now = func() time.Time { return now }
	binding := Binding{
		RequestID:   "otp_req_1",
		ChallengeID: "otp_ch_1",
		ExpiresAt:   now.Add(5 * time.Minute),
	}
	reference, err := sealer.Seal(Secret{Phone: "18013813909", Code: "123456"}, binding)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(reference, "18013813909") || strings.Contains(reference, "123456") {
		t.Fatal("sealed reference leaked plaintext")
	}
	secret, err := sealer.Open(reference, binding)
	if err != nil {
		t.Fatal(err)
	}
	if secret.Phone != "18013813909" || secret.Code != "123456" {
		t.Fatalf("unexpected secret: %#v", secret)
	}

	replacement := "A"
	if strings.HasSuffix(reference, replacement) {
		replacement = "B"
	}
	tampered := reference[:len(reference)-1] + replacement
	if _, err := sealer.Open(tampered, binding); !errors.Is(err, ErrInvalidReference) {
		t.Fatalf("tamper error = %v", err)
	}
	wrongBinding := binding
	wrongBinding.ChallengeID = "otp_ch_other"
	if _, err := sealer.Open(reference, wrongBinding); !errors.Is(err, ErrInvalidReference) {
		t.Fatalf("AAD error = %v", err)
	}
	sealer.now = func() time.Time { return binding.ExpiresAt }
	if _, err := sealer.Open(reference, binding); !errors.Is(err, ErrExpiredReference) {
		t.Fatalf("expiry error = %v", err)
	}
	sealer.now = func() time.Time { return now }
	unknownVersion := strings.Replace(reference, ".k1.", ".k2.", 1)
	if _, err := sealer.Open(unknownVersion, binding); !errors.Is(err, ErrUnknownKey) {
		t.Fatalf("unknown key error = %v", err)
	}
}
