package otpseal

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"
)

var (
	ErrInvalidReference = errors.New("otp code reference is invalid")
	ErrExpiredReference = errors.New("otp code reference is expired")
	ErrUnknownKey       = errors.New("otp code reference key version is unavailable")
)

type Binding struct {
	RequestID   string
	ChallengeID string
	ExpiresAt   time.Time
}

type Secret struct {
	Phone string `json:"phone"`
	Code  string `json:"code"`
}

type Sealer struct {
	activeVersion string
	keys          map[string][]byte
	random        io.Reader
	now           func() time.Time
}

func New(activeVersion string, keys map[string][]byte) (*Sealer, error) {
	active := strings.TrimSpace(activeVersion)
	if active == "" {
		return nil, fmt.Errorf("active otp code reference key version is required")
	}
	normalized := make(map[string][]byte, len(keys))
	for version, rawKey := range keys {
		version = strings.TrimSpace(version)
		if version == "" || len(rawKey) != 32 {
			return nil, fmt.Errorf("otp code reference key %q must be 32 bytes", version)
		}
		normalized[version] = append([]byte(nil), rawKey...)
	}
	if _, ok := normalized[active]; !ok {
		return nil, fmt.Errorf("active otp code reference key version %q is missing", active)
	}
	return &Sealer{
		activeVersion: active,
		keys:          normalized,
		random:        rand.Reader,
		now:           func() time.Time { return time.Now().UTC() },
	}, nil
}

func NewFromBase64(activeVersion string, encodedKeys map[string]string) (*Sealer, error) {
	keys := make(map[string][]byte, len(encodedKeys))
	for version, encoded := range encodedKeys {
		decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encoded))
		if err != nil {
			return nil, fmt.Errorf("decode otp code reference key %q: %w", version, err)
		}
		keys[version] = decoded
	}
	return New(activeVersion, keys)
}

func (s *Sealer) Seal(secret Secret, binding Binding) (string, error) {
	if s == nil || strings.TrimSpace(secret.Phone) == "" || strings.TrimSpace(secret.Code) == "" {
		return "", ErrInvalidReference
	}
	if err := validateBinding(binding); err != nil {
		return "", err
	}
	gcm, err := s.gcm(s.activeVersion)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(s.random, nonce); err != nil {
		return "", fmt.Errorf("generate otp code reference nonce: %w", err)
	}
	plaintext, err := json.Marshal(secret)
	if err != nil {
		return "", ErrInvalidReference
	}
	ciphertext := gcm.Seal(nil, nonce, plaintext, additionalData(binding))
	return strings.Join([]string{
		"otpref",
		"v1",
		s.activeVersion,
		base64.RawURLEncoding.EncodeToString(nonce),
		base64.RawURLEncoding.EncodeToString(ciphertext),
	}, "."), nil
}

func (s *Sealer) Open(reference string, binding Binding) (Secret, error) {
	if s == nil {
		return Secret{}, ErrInvalidReference
	}
	if err := validateBinding(binding); err != nil {
		return Secret{}, err
	}
	if !s.now().UTC().Before(binding.ExpiresAt.UTC()) {
		return Secret{}, ErrExpiredReference
	}
	parts := strings.Split(strings.TrimSpace(reference), ".")
	if len(parts) != 5 || parts[0] != "otpref" || parts[1] != "v1" {
		return Secret{}, ErrInvalidReference
	}
	gcm, err := s.gcm(parts[2])
	if err != nil {
		return Secret{}, err
	}
	nonce, err := decodeCanonicalRawURL(parts[3])
	if err != nil || len(nonce) != gcm.NonceSize() {
		return Secret{}, ErrInvalidReference
	}
	ciphertext, err := decodeCanonicalRawURL(parts[4])
	if err != nil {
		return Secret{}, ErrInvalidReference
	}
	plaintext, err := gcm.Open(nil, nonce, ciphertext, additionalData(binding))
	if err != nil {
		return Secret{}, ErrInvalidReference
	}
	var secret Secret
	if err := json.Unmarshal(plaintext, &secret); err != nil ||
		strings.TrimSpace(secret.Phone) == "" || strings.TrimSpace(secret.Code) == "" {
		return Secret{}, ErrInvalidReference
	}
	return secret, nil
}

func decodeCanonicalRawURL(encoded string) ([]byte, error) {
	if encoded == "" {
		return nil, ErrInvalidReference
	}
	decoded, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil || base64.RawURLEncoding.EncodeToString(decoded) != encoded {
		return nil, ErrInvalidReference
	}
	return decoded, nil
}

func (s *Sealer) gcm(version string) (cipher.AEAD, error) {
	key, ok := s.keys[strings.TrimSpace(version)]
	if !ok {
		return nil, ErrUnknownKey
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, ErrInvalidReference
	}
	return cipher.NewGCM(block)
}

func validateBinding(binding Binding) error {
	if strings.TrimSpace(binding.RequestID) == "" ||
		strings.TrimSpace(binding.ChallengeID) == "" ||
		binding.ExpiresAt.IsZero() {
		return ErrInvalidReference
	}
	return nil
}

func additionalData(binding Binding) []byte {
	return []byte(strings.Join([]string{
		strings.TrimSpace(binding.RequestID),
		strings.TrimSpace(binding.ChallengeID),
		binding.ExpiresAt.UTC().Format(time.RFC3339),
	}, "\n"))
}
