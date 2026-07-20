package persistence

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"io"
	"strings"

	runtimeconfig "quwoquan_service/runtime/config"
	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
	registrationports "quwoquan_service/services/user-service/internal/domain/account/device_registration/ports"
)

type AESGCMTokenCipher struct {
	aead   cipher.AEAD
	key    []byte
	random io.Reader
}

const pushTokenEncryptionKeyConfig = "QWQ_PUSH_TOKEN_ENCRYPTION_KEY"

func LoadAESGCMTokenCipher(
	provider runtimeconfig.RuntimeConfigProvider,
) (*AESGCMTokenCipher, error) {
	if provider == nil {
		return nil, errors.New("DeviceRegistration runtime config is required")
	}
	encoded, ok := provider.GetString(pushTokenEncryptionKeyConfig)
	if !ok {
		return nil, errors.New(pushTokenEncryptionKeyConfig + " is required")
	}
	key, err := base64.StdEncoding.DecodeString(strings.TrimSpace(encoded))
	if err != nil {
		return nil, errors.New("DeviceRegistration encryption key is invalid")
	}
	return NewAESGCMTokenCipher(key)
}

func NewAESGCMTokenCipher(key []byte) (*AESGCMTokenCipher, error) {
	if len(key) != 32 {
		return nil, errors.New("DeviceRegistration token cipher requires a 32-byte key")
	}
	block, err := aes.NewCipher(append([]byte(nil), key...))
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &AESGCMTokenCipher{
		aead:   aead,
		key:    append([]byte(nil), key...),
		random: rand.Reader,
	}, nil
}

var _ registrationports.TokenCipher = (*AESGCMTokenCipher)(nil)

func (tokenCipher *AESGCMTokenCipher) ProtectPushToken(
	ctx context.Context,
	plaintext []byte,
	scope registrationports.TokenCipherScope,
) (string, string, error) {
	if tokenCipher == nil || tokenCipher.aead == nil || tokenCipher.random == nil {
		return "", "", errors.New("DeviceRegistration token cipher is unavailable")
	}
	scope.AccountID = strings.TrimSpace(scope.AccountID)
	scope.DeviceID = strings.TrimSpace(scope.DeviceID)
	scope.Kind = registrationmodel.EndpointKind(
		strings.TrimSpace(string(scope.Kind)),
	)
	if len(plaintext) == 0 ||
		scope.AccountID == "" ||
		scope.DeviceID == "" ||
		!scope.Kind.Valid() {
		return "", "", errors.New("DeviceRegistration token encryption input is incomplete")
	}
	select {
	case <-ctx.Done():
		return "", "", ctx.Err()
	default:
	}
	nonce := make([]byte, tokenCipher.aead.NonceSize())
	if _, err := io.ReadFull(tokenCipher.random, nonce); err != nil {
		return "", "", err
	}
	additionalData := tokenCipherAdditionalData(scope)
	sealed := tokenCipher.aead.Seal(nonce, nonce, plaintext, additionalData)
	mac := hmac.New(sha256.New, tokenCipher.key)
	_, _ = mac.Write(plaintext)
	return base64.RawURLEncoding.EncodeToString(sealed),
		hex.EncodeToString(mac.Sum(nil)),
		nil
}

func (tokenCipher *AESGCMTokenCipher) RevealPushToken(
	ctx context.Context,
	ciphertext string,
	scope registrationports.TokenCipherScope,
) ([]byte, error) {
	if tokenCipher == nil || tokenCipher.aead == nil {
		return nil, errors.New("DeviceRegistration token cipher is unavailable")
	}
	scope.AccountID = strings.TrimSpace(scope.AccountID)
	scope.DeviceID = strings.TrimSpace(scope.DeviceID)
	scope.Kind = registrationmodel.EndpointKind(
		strings.TrimSpace(string(scope.Kind)),
	)
	ciphertext = strings.TrimSpace(ciphertext)
	if ciphertext == "" ||
		scope.AccountID == "" ||
		scope.DeviceID == "" ||
		!scope.Kind.Valid() {
		return nil, errors.New("DeviceRegistration token decryption input is incomplete")
	}
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}
	sealed, err := base64.RawURLEncoding.DecodeString(ciphertext)
	if err != nil || len(sealed) <= tokenCipher.aead.NonceSize() {
		return nil, errors.New("DeviceRegistration token ciphertext is invalid")
	}
	nonce := sealed[:tokenCipher.aead.NonceSize()]
	body := sealed[tokenCipher.aead.NonceSize():]
	plaintext, err := tokenCipher.aead.Open(
		nil,
		nonce,
		body,
		tokenCipherAdditionalData(scope),
	)
	if err != nil {
		return nil, errors.New("DeviceRegistration token authentication failed")
	}
	return plaintext, nil
}

func tokenCipherAdditionalData(scope registrationports.TokenCipherScope) []byte {
	return []byte(
		scope.AccountID + "\x00" +
			scope.DeviceID + "\x00" +
			string(scope.Kind),
	)
}
