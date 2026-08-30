package application

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"strings"
)

type Ed25519Signer struct {
	keyID   string
	key     ed25519.PrivateKey
	testKey bool
}

func NewEd25519Signer(keyID string, privateKey []byte, testKey bool) (*Ed25519Signer, error) {
	keyID = strings.TrimSpace(keyID)
	if keyID == "" || len(privateKey) != ed25519.PrivateKeySize {
		return nil, errors.New("human authority signer requires key id and Ed25519 private key")
	}
	return &Ed25519Signer{keyID: keyID, key: append(ed25519.PrivateKey(nil), privateKey...), testKey: testKey}, nil
}
func (s *Ed25519Signer) KeyID() string { return s.keyID }
func (s *Ed25519Signer) PublicKey() []byte {
	return append([]byte(nil), s.key.Public().(ed25519.PublicKey)...)
}
func (s *Ed25519Signer) TestKey() bool                   { return s.testKey }
func (s *Ed25519Signer) Sign(raw []byte) ([]byte, error) { return ed25519.Sign(s.key, raw), nil }

func LoadEd25519Signer(keyID, filePath, encoded string, testKey bool) (*Ed25519Signer, error) {
	filePath, encoded = strings.TrimSpace(filePath), strings.TrimSpace(encoded)
	if (filePath == "") == (encoded == "") {
		return nil, errors.New("human authority signer requires exactly one key source")
	}
	var raw []byte
	var err error
	if filePath != "" {
		raw, err = os.ReadFile(filePath)
		if err != nil {
			return nil, fmt.Errorf("read human authority signing key: %w", err)
		}
	} else {
		raw, err = base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			return nil, errors.New("human authority signing key base64 is invalid")
		}
	}
	if block, _ := pem.Decode(raw); block != nil {
		raw = block.Bytes
	}
	if len(raw) == ed25519.SeedSize {
		raw = ed25519.NewKeyFromSeed(raw)
	}
	return NewEd25519Signer(keyID, raw, testKey)
}
