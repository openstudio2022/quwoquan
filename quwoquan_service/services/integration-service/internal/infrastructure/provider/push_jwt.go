package provider

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"os"
	"strings"
)

func loadP256PrivateKeyFile(path string) (*ecdsa.PrivateKey, error) {
	raw, err := readSecretFile(path)
	if err != nil {
		return nil, err
	}
	block, _ := pem.Decode(raw)
	clear(raw)
	if block == nil {
		return nil, errors.New("APNs key file does not contain PEM data")
	}
	var key *ecdsa.PrivateKey
	switch block.Type {
	case "PRIVATE KEY":
		parsed, parseErr := x509.ParsePKCS8PrivateKey(block.Bytes)
		if parseErr != nil {
			return nil, fmt.Errorf("parse APNs PKCS8 key: %w", parseErr)
		}
		var ok bool
		key, ok = parsed.(*ecdsa.PrivateKey)
		if !ok {
			return nil, errors.New("APNs key file is not an EC private key")
		}
	case "EC PRIVATE KEY":
		key, err = x509.ParseECPrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("parse APNs EC key: %w", err)
		}
	default:
		return nil, errors.New("APNs key file must contain PRIVATE KEY or EC PRIVATE KEY")
	}
	if key.Curve != elliptic.P256() {
		return nil, errors.New("APNs key must use P-256")
	}
	return key, nil
}

func loadRSAPrivateKeyFile(path string) (*rsa.PrivateKey, error) {
	raw, err := readSecretFile(path)
	if err != nil {
		return nil, err
	}
	defer clear(raw)
	return parseRSAPrivateKeyPEM(raw)
}

func parseRSAPrivateKeyPEM(raw []byte) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode(raw)
	if block == nil {
		return nil, errors.New("FCM service-account key does not contain PEM data")
	}
	switch block.Type {
	case "PRIVATE KEY":
		parsed, parseErr := x509.ParsePKCS8PrivateKey(block.Bytes)
		if parseErr != nil {
			return nil, fmt.Errorf("parse FCM PKCS8 key: %w", parseErr)
		}
		key, ok := parsed.(*rsa.PrivateKey)
		if !ok {
			return nil, errors.New("FCM service-account key is not RSA")
		}
		return key, key.Validate()
	case "RSA PRIVATE KEY":
		key, parseErr := x509.ParsePKCS1PrivateKey(block.Bytes)
		if parseErr != nil {
			return nil, fmt.Errorf("parse FCM PKCS1 key: %w", parseErr)
		}
		return key, key.Validate()
	default:
		return nil, errors.New("FCM service-account key must contain PRIVATE KEY or RSA PRIVATE KEY")
	}
}

func readSecretFile(path string) ([]byte, error) {
	normalized := strings.TrimSpace(path)
	if normalized == "" {
		return nil, errors.New("secret file path is required")
	}
	raw, err := os.ReadFile(normalized)
	if err != nil {
		return nil, fmt.Errorf("read secret file: %w", err)
	}
	if len(raw) == 0 {
		return nil, errors.New("secret file is empty")
	}
	return raw, nil
}

func signES256JWT(
	privateKey *ecdsa.PrivateKey,
	header any,
	claims any,
) (string, error) {
	signingInput, err := jwtSigningInput(header, claims)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256([]byte(signingInput))
	r, s, err := ecdsa.Sign(rand.Reader, privateKey, digest[:])
	if err != nil {
		return "", fmt.Errorf("sign ES256 JWT: %w", err)
	}
	signature := make([]byte, 64)
	fillPaddedInteger(signature[:32], r)
	fillPaddedInteger(signature[32:], s)
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(signature), nil
}

func signRS256JWT(
	privateKey *rsa.PrivateKey,
	header any,
	claims any,
) (string, error) {
	signingInput, err := jwtSigningInput(header, claims)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256([]byte(signingInput))
	signature, err := rsa.SignPKCS1v15(rand.Reader, privateKey, crypto.SHA256, digest[:])
	if err != nil {
		return "", fmt.Errorf("sign RS256 JWT: %w", err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(signature), nil
}

func jwtSigningInput(header any, claims any) (string, error) {
	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("encode JWT header: %w", err)
	}
	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("encode JWT claims: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(headerJSON) + "." +
		base64.RawURLEncoding.EncodeToString(claimsJSON), nil
}

func fillPaddedInteger(target []byte, value *big.Int) {
	raw := value.Bytes()
	copy(target[len(target)-len(raw):], raw)
}
