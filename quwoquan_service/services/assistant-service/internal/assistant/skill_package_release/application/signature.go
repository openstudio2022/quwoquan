package application

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type Ed25519Verifier struct {
	trustedKeys map[string]ed25519.PublicKey
}

func NewEd25519Verifier(trustedKeys map[string]ed25519.PublicKey) *Ed25519Verifier {
	keys := make(map[string]ed25519.PublicKey, len(trustedKeys))
	for keyID, publicKey := range trustedKeys {
		keyID = strings.TrimSpace(keyID)
		if keyID == "" || len(publicKey) != ed25519.PublicKeySize {
			continue
		}
		keys[keyID] = append(ed25519.PublicKey(nil), publicKey...)
	}
	return &Ed25519Verifier{trustedKeys: keys}
}

func (verifier *Ed25519Verifier) Verify(
	_ context.Context,
	release model.Release,
) error {
	if verifier == nil || release.Signature.Algorithm != "ed25519" {
		return errors.New("unsupported skill package signature")
	}
	publicKey, trusted := verifier.trustedKeys[release.Signature.KeyID]
	if !trusted {
		return errors.New("skill package signing key is not trusted")
	}
	signature, err := base64.StdEncoding.DecodeString(release.Signature.Value)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return errors.New("malformed skill package signature")
	}
	if !ed25519.Verify(
		publicKey,
		[]byte(release.ReleaseDigest),
		signature,
	) {
		return errors.New("skill package signature verification failed")
	}
	return nil
}
