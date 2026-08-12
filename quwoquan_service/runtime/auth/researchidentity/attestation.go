package researchidentity

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"regexp"
	"strings"
	"time"
)

const (
	subjectDigestDomain = "qwq-research-subject-v1"
	maximumTTL          = 15 * time.Minute
)

var payloadPattern = regexp.MustCompile(
	`^v1\.(sha256:[0-9a-f]{64})\.` +
		`([0-9]{4}-[0-9]{2}-[0-9]{2}T[^Z]+Z)\.` +
		`([0-9]{4}-[0-9]{2}-[0-9]{2}T[^Z]+Z)\.` +
		`([0-9a-f]{64})$`,
)

var ErrInvalidAttestation = errors.New("research identity attestation is invalid")

// Authority is the single execution-code identity for issuing and verifying
// short-lived Alpha Research attestations. Its key is never exposed.
type Authority struct {
	key []byte
}

type VerifiedAttestation struct {
	SubjectHash       string
	AttestationIDHash string
	IssuedAt          time.Time
	ExpiresAt         time.Time
}

func NewAuthority(key []byte) (*Authority, error) {
	if len(key) < 32 {
		return nil, errors.New("research identity attestation key must contain at least 32 bytes")
	}
	return &Authority{key: append([]byte(nil), key...)}, nil
}

func (authority *Authority) Issue(
	accountID string,
	issuedAt time.Time,
	expiresAt time.Time,
	nonce []byte,
) (VerifiedAttestation, string, error) {
	accountID = strings.TrimSpace(accountID)
	issuedAt = issuedAt.UTC()
	expiresAt = expiresAt.UTC()
	if authority == nil || len(authority.key) < 32 || accountID == "" ||
		len(nonce) != 32 || !expiresAt.After(issuedAt) ||
		expiresAt.Sub(issuedAt) > maximumTTL {
		return VerifiedAttestation{}, "", ErrInvalidAttestation
	}
	subjectHash := authority.subjectHash(accountID)
	payload := strings.Join([]string{
		"v1",
		subjectHash,
		issuedAt.Format(time.RFC3339Nano),
		expiresAt.Format(time.RFC3339Nano),
		hex.EncodeToString(nonce),
	}, ".")
	mac := hmac.New(sha256.New, authority.key)
	_, _ = mac.Write([]byte(payload))
	token := base64.RawURLEncoding.EncodeToString([]byte(payload)) + "." +
		base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return verified(subjectHash, token, issuedAt, expiresAt), token, nil
}

func (authority *Authority) Verify(
	accountID string,
	token string,
	now time.Time,
) (VerifiedAttestation, error) {
	accountID = strings.TrimSpace(accountID)
	token = strings.TrimSpace(token)
	if authority == nil || len(authority.key) < 32 || accountID == "" || token == "" {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	segments := strings.Split(token, ".")
	if len(segments) != 2 {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	payload, err := base64.RawURLEncoding.DecodeString(segments[0])
	if err != nil {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	signature, err := base64.RawURLEncoding.DecodeString(segments[1])
	if err != nil {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	mac := hmac.New(sha256.New, authority.key)
	_, _ = mac.Write(payload)
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	parts := payloadPattern.FindStringSubmatch(string(payload))
	if len(parts) != 5 || !hmac.Equal(
		[]byte(parts[1]),
		[]byte(authority.subjectHash(accountID)),
	) {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	issuedAt, issuedErr := time.Parse(time.RFC3339Nano, parts[2])
	expiresAt, expiresErr := time.Parse(time.RFC3339Nano, parts[3])
	now = now.UTC()
	if issuedErr != nil || expiresErr != nil || !expiresAt.After(issuedAt) ||
		expiresAt.Sub(issuedAt) > maximumTTL || issuedAt.After(now.Add(30*time.Second)) ||
		!expiresAt.After(now) {
		return VerifiedAttestation{}, ErrInvalidAttestation
	}
	return verified(parts[1], token, issuedAt, expiresAt), nil
}

func (authority *Authority) subjectHash(accountID string) string {
	mac := hmac.New(sha256.New, authority.key)
	_, _ = mac.Write([]byte(subjectDigestDomain + "\x00" + accountID))
	return "sha256:" + hex.EncodeToString(mac.Sum(nil))
}

func verified(
	subjectHash string,
	token string,
	issuedAt time.Time,
	expiresAt time.Time,
) VerifiedAttestation {
	digest := sha256.Sum256([]byte(token))
	return VerifiedAttestation{
		SubjectHash:       subjectHash,
		AttestationIDHash: "sha256:" + hex.EncodeToString(digest[:]),
		IssuedAt:          issuedAt,
		ExpiresAt:         expiresAt,
	}
}
