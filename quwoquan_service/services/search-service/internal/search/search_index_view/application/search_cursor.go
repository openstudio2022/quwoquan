package application

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

const (
	searchCursorVersion = 1
	searchCursorTTL     = 15 * time.Minute
	maxSearchCursorSize = 4096
)

var ErrSearchCursor = errors.New("invalid search cursor")

type SearchCursorCodec struct {
	aead cipher.AEAD
	now  func() time.Time
}

type searchCursorEnvelope struct {
	Version         int    `json:"version"`
	QueryDigest     string `json:"queryDigest"`
	ScopeDigest     string `json:"scopeDigest"`
	PrincipalDigest string `json:"principalDigest"`
	CandidateDigest string `json:"candidateDigest"`
	PolicyDigest    string `json:"policyDigest"`
	Offset          int    `json:"offset"`
	// PITID pins every follow-up page to the point-in-time snapshot the
	// pagination started on (lazy: opened on the first follow-up page). An
	// expired snapshot fails the whole cursor closed — pagination never
	// silently degrades to an unsnapshotted query.
	PITID     string `json:"pitId,omitempty"`
	ExpiresAt int64  `json:"expiresAt"`
}

type objectReferenceEnvelope struct {
	Version    int    `json:"version"`
	ObjectType string `json:"objectType"`
	ObjectID   string `json:"objectId"`
}

func NewSearchCursorCodec(rootSecret []byte) (*SearchCursorCodec, error) {
	if len(rootSecret) < 32 {
		return nil, errors.New("search cursor root secret must contain at least 32 bytes")
	}
	keyInput := append([]byte("search-index-view-owner-query-v1\x00"), rootSecret...)
	key := sha256.Sum256(keyInput)
	block, err := aes.NewCipher(key[:])
	if err != nil {
		return nil, fmt.Errorf("initialize search cursor cipher: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("initialize search cursor AEAD: %w", err)
	}
	return &SearchCursorCodec{aead: aead, now: time.Now}, nil
}

func (codec *SearchCursorCodec) encodeCursor(
	in QueryInput,
	caller QueryCaller,
	identity QueryExecutionIdentity,
	offset int,
	pitID string,
) (string, error) {
	if codec == nil || codec.aead == nil || offset <= 0 {
		return "", ErrSearchCursor
	}
	queryDigest, scopeDigest, principalDigest, err := cursorBindingDigests(in, caller, identity)
	if err != nil {
		return "", err
	}
	payload, err := json.Marshal(searchCursorEnvelope{
		Version: searchCursorVersion, QueryDigest: queryDigest,
		ScopeDigest: scopeDigest, PrincipalDigest: principalDigest,
		CandidateDigest: identity.CandidateDigest, PolicyDigest: identity.PolicyDigest,
		Offset: offset, PITID: strings.TrimSpace(pitID),
		ExpiresAt: codec.now().UTC().Add(searchCursorTTL).Unix(),
	})
	if err != nil {
		return "", fmt.Errorf("encode search cursor: %w", err)
	}
	return codec.seal("search-cursor", payload)
}

func (codec *SearchCursorCodec) decodeCursor(
	token string,
	in QueryInput,
	caller QueryCaller,
	identity QueryExecutionIdentity,
) (int, string, error) {
	if codec == nil || codec.aead == nil || strings.TrimSpace(token) == "" || len(token) > maxSearchCursorSize {
		return 0, "", ErrSearchCursor
	}
	payload, err := codec.open("search-cursor", token)
	if err != nil {
		return 0, "", ErrSearchCursor
	}
	var envelope searchCursorEnvelope
	if err := json.Unmarshal(payload, &envelope); err != nil {
		return 0, "", ErrSearchCursor
	}
	queryDigest, scopeDigest, principalDigest, err := cursorBindingDigests(in, caller, identity)
	if err != nil {
		return 0, "", err
	}
	if envelope.Version != searchCursorVersion || envelope.Offset <= 0 ||
		envelope.ExpiresAt <= codec.now().UTC().Unix() ||
		envelope.QueryDigest != queryDigest || envelope.ScopeDigest != scopeDigest ||
		envelope.PrincipalDigest != principalDigest ||
		envelope.CandidateDigest != identity.CandidateDigest ||
		envelope.PolicyDigest != identity.PolicyDigest {
		return 0, "", ErrSearchCursor
	}
	return envelope.Offset, envelope.PITID, nil
}

func (codec *SearchCursorCodec) encodeObjectReference(objectType, objectID string) (string, error) {
	objectType = strings.TrimSpace(objectType)
	objectID = strings.TrimSpace(objectID)
	if codec == nil || codec.aead == nil || objectType == "" || objectID == "" {
		return "", errors.New("search object reference identity is invalid")
	}
	payload, err := json.Marshal(objectReferenceEnvelope{
		Version: searchCursorVersion, ObjectType: objectType, ObjectID: objectID,
	})
	if err != nil {
		return "", fmt.Errorf("encode search object reference: %w", err)
	}
	return codec.seal("search-object-ref", payload)
}

func (codec *SearchCursorCodec) seal(purpose string, payload []byte) (string, error) {
	nonce := make([]byte, codec.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", fmt.Errorf("generate %s nonce: %w", purpose, err)
	}
	sealed := codec.aead.Seal(nil, nonce, payload, []byte(purpose))
	packed := append(nonce, sealed...)
	return base64.RawURLEncoding.EncodeToString(packed), nil
}

func (codec *SearchCursorCodec) open(purpose, token string) ([]byte, error) {
	packed, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(token))
	if err != nil || len(packed) <= codec.aead.NonceSize() {
		return nil, ErrSearchCursor
	}
	nonce := packed[:codec.aead.NonceSize()]
	return codec.aead.Open(nil, nonce, packed[codec.aead.NonceSize():], []byte(purpose))
}

func cursorBindingDigests(
	in QueryInput,
	caller QueryCaller,
	identity QueryExecutionIdentity,
) (string, string, string, error) {
	principal := strings.TrimSpace(caller.PrincipalKey)
	if principal == "" || !canonicalDigest(identity.CandidateDigest) || !canonicalDigest(identity.PolicyDigest) {
		return "", "", "", ErrSearchCursor
	}
	normalizedQuery := rtsearch.Analyze(in.Query, in.ObjectTypes).Normalized
	queryDigest := digestJSON(normalizedQuery)
	objectTypes := normalizedSorted(in.ObjectTypes)
	contentTypes := normalizedSorted(in.ContentTypes)
	ids := normalizedSorted(in.IDs)
	tags := normalizedSorted(in.Tags)
	scopeDigest := digestJSON(struct {
		Mode         string   `json:"mode"`
		ObjectTypes  []string `json:"objectTypes"`
		ContentTypes []string `json:"contentTypes"`
		IDs          []string `json:"ids"`
		Tags         []string `json:"tags"`
		TimeRange    any      `json:"timeRange,omitempty"`
		Near         any      `json:"near,omitempty"`
		Limit        int      `json:"limit"`
	}{
		Mode: strings.ToLower(strings.TrimSpace(in.Mode)), ObjectTypes: objectTypes,
		ContentTypes: contentTypes,
		IDs:          ids, Tags: tags, TimeRange: in.TimeRange, Near: in.Near, Limit: in.Limit,
	})
	return queryDigest, scopeDigest, digestJSON(principal), nil
}

func normalizedSorted(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.ToLower(strings.TrimSpace(value)); value != "" {
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}

func digestJSON(value any) string {
	encoded, _ := json.Marshal(value)
	return fmt.Sprintf("sha256:%x", sha256.Sum256(encoded))
}

func canonicalDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+64 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, r := range value[len("sha256:"):] {
		if !strings.ContainsRune("0123456789abcdef", r) {
			return false
		}
	}
	return true
}
