package trust

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"quwoquan_service/internal/metadata/readiness"
)

func decodeStrict(data []byte, target any, name string) error {
	if err := readiness.RejectDuplicateJSONKeys(data); err != nil {
		return fmt.Errorf("decode %s: %w", name, err)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode %s: %w", name, err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return fmt.Errorf("decode %s: trailing JSON document", name)
		}
		return fmt.Errorf("decode %s trailing content: %w", name, err)
	}
	return nil
}

func decodePublicKey(value string) (ed25519.PublicKey, error) {
	decoded, err := base64.StdEncoding.Strict().DecodeString(value)
	if err != nil || len(decoded) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("publicKey must be one base64 Ed25519 public key")
	}
	return ed25519.PublicKey(decoded), nil
}

func decodeSignature(value string) ([]byte, error) {
	decoded, err := base64.StdEncoding.Strict().DecodeString(value)
	if err != nil || len(decoded) != ed25519.SignatureSize {
		return nil, fmt.Errorf("signature must be one base64 Ed25519 signature")
	}
	return decoded, nil
}

func validIdentity(value string) bool {
	if len(value) == 0 || len(value) > 128 {
		return false
	}
	for index, current := range value {
		if current >= 'a' && current <= 'z' || current >= 'A' && current <= 'Z' ||
			current >= '0' && current <= '9' {
			continue
		}
		if index > 0 && (current == '.' || current == '_' || current == '-' || current == '/') {
			continue
		}
		return false
	}
	return !strings.Contains(value, "//")
}

func isSHA256(value string) bool {
	return len(value) == 64 && isLowerHex(value)
}

func isDigest(value string) bool {
	return len(value) == 71 && strings.HasPrefix(value, "sha256:") &&
		isLowerHex(strings.TrimPrefix(value, "sha256:"))
}

func isCommitSHA(value string) bool {
	return (len(value) == 40 || len(value) == 64) && isLowerHex(value)
}

func isLowerHex(value string) bool {
	for _, current := range value {
		if (current < '0' || current > '9') && (current < 'a' || current > 'f') {
			return false
		}
	}
	return true
}
