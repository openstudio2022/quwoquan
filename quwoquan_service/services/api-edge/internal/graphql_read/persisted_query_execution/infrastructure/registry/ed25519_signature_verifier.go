package registry

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"fmt"
	"regexp"
)

const maxSignatureKeyIDBytes = 128

var signatureKeyIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

// Ed25519SignatureVerifier verifies persisted-query release registries against
// a startup-validated, immutable public-key set.
type Ed25519SignatureVerifier struct {
	publicKeys map[string]ed25519.PublicKey
}

// NewEd25519SignatureVerifier decodes the configured standard-base64 public
// keys once. Key IDs and key bytes are deliberately not normalized: accepting
// alternate spellings would make release-signature selection ambiguous.
func NewEd25519SignatureVerifier(
	encodedPublicKeys map[string]string,
) (*Ed25519SignatureVerifier, error) {
	if len(encodedPublicKeys) == 0 {
		return nil, errors.New("at least one persisted query registry public key is required")
	}
	publicKeys := make(map[string]ed25519.PublicKey, len(encodedPublicKeys))
	for keyID, encoded := range encodedPublicKeys {
		if len(keyID) == 0 || len(keyID) > maxSignatureKeyIDBytes ||
			!signatureKeyIDPattern.MatchString(keyID) {
			return nil, fmt.Errorf("invalid persisted query registry public key id %q", keyID)
		}
		decoded, err := base64.StdEncoding.Strict().DecodeString(encoded)
		if err != nil {
			return nil, fmt.Errorf("decode persisted query registry public key %q: %w", keyID, err)
		}
		if base64.StdEncoding.EncodeToString(decoded) != encoded {
			return nil, fmt.Errorf(
				"persisted query registry public key %q must use canonical base64", keyID,
			)
		}
		if len(decoded) != ed25519.PublicKeySize {
			return nil, fmt.Errorf(
				"persisted query registry public key %q has length %d, want %d",
				keyID, len(decoded), ed25519.PublicKeySize,
			)
		}
		publicKeys[keyID] = append(ed25519.PublicKey(nil), decoded...)
	}
	return &Ed25519SignatureVerifier{publicKeys: publicKeys}, nil
}

func (verifier *Ed25519SignatureVerifier) Verify(
	ctx context.Context,
	keyID string,
	payload []byte,
	signature []byte,
) error {
	if verifier == nil {
		return errors.New("persisted query registry signature verifier is nil")
	}
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("persisted query registry signature verification canceled: %w", err)
	}
	publicKey, ok := verifier.publicKeys[keyID]
	if !ok {
		return fmt.Errorf("persisted query registry signature key %q is not configured", keyID)
	}
	if len(signature) != ed25519.SignatureSize {
		return fmt.Errorf(
			"persisted query registry signature has length %d, want %d",
			len(signature), ed25519.SignatureSize,
		)
	}
	if !ed25519.Verify(publicKey, payload, signature) {
		return errors.New("persisted query registry Ed25519 signature is invalid")
	}
	return nil
}
