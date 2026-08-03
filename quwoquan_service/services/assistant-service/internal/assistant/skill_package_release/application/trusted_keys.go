package application

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
)

const maxTrustedSkillPackageKeys = 16

func DecodeTrustedPublicKeys(raw string) (map[string]ed25519.PublicKey, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("trusted Skill package public keys are required")
	}
	encoded := map[string]string{}
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&encoded); err != nil {
		return nil, fmt.Errorf("decode trusted Skill package public keys: %w", err)
	}
	if len(encoded) == 0 || len(encoded) > maxTrustedSkillPackageKeys {
		return nil, fmt.Errorf("trusted Skill package public key count is invalid")
	}
	keys := make(map[string]ed25519.PublicKey, len(encoded))
	for keyID, value := range encoded {
		keyID = strings.TrimSpace(keyID)
		decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(value))
		if keyID == "" || err != nil || len(decoded) != ed25519.PublicKeySize {
			return nil, fmt.Errorf("trusted Skill package public key %q is invalid", keyID)
		}
		keys[keyID] = append(ed25519.PublicKey(nil), decoded...)
	}
	return keys, nil
}
