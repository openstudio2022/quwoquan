package persona_relationship

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var ErrInvalidReadCursor = errors.New("persona relationship read cursor is invalid")

type ReadCursorClaims struct {
	OwnerPersonaID  string    `json:"own"`
	ViewerPersonaID string    `json:"vwr"`
	Direction       string    `json:"dir"`
	Query           string    `json:"qry"`
	PositionAt      time.Time `json:"pos"`
	PositionPairID  string    `json:"pid"`
}

type ReadCursorSigner struct{ key []byte }

func NewReadCursorSigner(key []byte) (*ReadCursorSigner, error) {
	if len(key) < 32 {
		return nil, errors.New("relationship read cursor key must carry at least 32 bytes")
	}
	return &ReadCursorSigner{key: append([]byte(nil), key...)}, nil
}

func (s *ReadCursorSigner) Issue(claims ReadCursorClaims) (string, error) {
	claims = normalizeReadCursorClaims(claims)
	if claims.OwnerPersonaID == "" || claims.Direction == "" || claims.PositionAt.IsZero() || claims.PositionPairID == "" {
		return "", ErrInvalidReadCursor
	}
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	signature := s.sign(payload)
	return base64.RawURLEncoding.EncodeToString(payload) + "." + base64.RawURLEncoding.EncodeToString(signature), nil
}

func (s *ReadCursorSigner) Verify(token string, expected ReadCursorClaims) (ReadCursorClaims, error) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 2 {
		return ReadCursorClaims{}, ErrInvalidReadCursor
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return ReadCursorClaims{}, ErrInvalidReadCursor
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || !hmac.Equal(signature, s.sign(payload)) {
		return ReadCursorClaims{}, ErrInvalidReadCursor
	}
	var actual ReadCursorClaims
	if err := json.Unmarshal(payload, &actual); err != nil {
		return ReadCursorClaims{}, ErrInvalidReadCursor
	}
	actual = normalizeReadCursorClaims(actual)
	expected = normalizeReadCursorClaims(expected)
	if actual.OwnerPersonaID == "" || actual.Direction == "" || actual.PositionAt.IsZero() || actual.PositionPairID == "" ||
		actual.OwnerPersonaID != expected.OwnerPersonaID || actual.ViewerPersonaID != expected.ViewerPersonaID ||
		actual.Direction != expected.Direction || actual.Query != expected.Query {
		return ReadCursorClaims{}, ErrInvalidReadCursor
	}
	return actual, nil
}

func (s *ReadCursorSigner) sign(payload []byte) []byte {
	mac := hmac.New(sha256.New, s.key)
	mac.Write([]byte("quwoquan.user.relationship.read_cursor.v1\x1f"))
	mac.Write(payload)
	return mac.Sum(nil)
}

func normalizeReadCursorClaims(claims ReadCursorClaims) ReadCursorClaims {
	claims.OwnerPersonaID = strings.TrimSpace(claims.OwnerPersonaID)
	claims.ViewerPersonaID = strings.TrimSpace(claims.ViewerPersonaID)
	claims.Direction = strings.TrimSpace(claims.Direction)
	claims.Query = normalizeRelationshipQuery(claims.Query)
	claims.PositionAt = claims.PositionAt.UTC()
	claims.PositionPairID = strings.TrimSpace(claims.PositionPairID)
	return claims
}

func normalizeRelationshipQuery(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(value))), " ")
}
