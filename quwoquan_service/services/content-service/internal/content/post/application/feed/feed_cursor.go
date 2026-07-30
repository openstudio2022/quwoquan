package feed

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	cryptorand "crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/identity"
)

const (
	feedCursorPrefix              = "fc."
	feedCursorMaximumWireBytes    = 4096
	FeedCursorMaximumDepth        = 50
	FeedCursorTTL                 = 10 * time.Minute
	feedCursorKeyDerivationDomain = "quwoquan.content.feed.cursor.aes-gcm"
)

var ErrInvalidFeedCursor = errors.New("invalid or expired feed cursor")

type feedCursorKind string

const (
	feedCursorKindRecommendation feedCursorKind = "recommendation"
	feedCursorKindPostReader     feedCursorKind = "post_reader"
	feedCursorKindDeliveryPage   feedCursorKind = "delivery_page"
)

type feedCursorEnvelope struct {
	Kind                  feedCursorKind `json:"kind"`
	Value                 string         `json:"value,omitempty"`
	WindowID              string         `json:"windowId,omitempty"`
	AfterOrdinal          int            `json:"afterOrdinal,omitempty"`
	AfterContentID        string         `json:"afterContentId,omitempty"`
	DeliveryPageID        string         `json:"deliveryPageId,omitempty"`
	DeliveryPageExpiresAt int64          `json:"deliveryPageExpiresAt,omitempty"`
	FeedRequestID         string         `json:"feedRequestId,omitempty"`
	ReleaseID             string         `json:"releaseId,omitempty"`
	ManifestDigest        string         `json:"manifestDigest,omitempty"`
	Depth                 int            `json:"depth"`
	ExpiresAt             int64          `json:"expiresAt"`
}

type postReaderFeedCursorState struct {
	PostID         string
	ReleaseID      string
	ManifestDigest string
	Depth          int
}

// FeedCursorCodec seals the cursor payload with AES-GCM. The request scope is
// authenticated as additional data rather than serialized into the token, so
// actor/session/channel context cannot be inspected or changed by the client.
type FeedCursorCodec struct {
	aead     cipher.AEAD
	now      func() time.Time
	ttl      time.Duration
	maxDepth int
}

type FeedCursorCodecOption func(*FeedCursorCodec) error

// WithFeedCursorTTL is primarily useful for deterministic contract tests. The
// production composition intentionally omits it and therefore uses the TTL
// declared by the discovery-feed contract.
func WithFeedCursorTTL(ttl time.Duration) FeedCursorCodecOption {
	return func(codec *FeedCursorCodec) error {
		if ttl <= 0 {
			return fmt.Errorf("feed cursor TTL must be positive")
		}
		codec.ttl = ttl
		return nil
	}
}

// WithFeedCursorClock keeps expiry tests deterministic without weakening the
// production 600-second ranked-window contract.
func WithFeedCursorClock(now func() time.Time) FeedCursorCodecOption {
	return func(codec *FeedCursorCodec) error {
		if now == nil {
			return fmt.Errorf("feed cursor clock is required")
		}
		codec.now = func() time.Time { return now().UTC() }
		return nil
	}
}

// WithFeedCursorDepthLimit allows tests to exercise the continuation boundary
// without generating fifty pages. Production uses FeedCursorMaximumDepth.
func WithFeedCursorDepthLimit(maxDepth int) FeedCursorCodecOption {
	return func(codec *FeedCursorCodec) error {
		if maxDepth <= 0 || maxDepth > FeedCursorMaximumDepth {
			return fmt.Errorf("feed cursor depth limit must be within [1,%d]", FeedCursorMaximumDepth)
		}
		codec.maxDepth = maxDepth
		return nil
	}
}

func NewFeedCursorCodec(rootSecret []byte, opts ...FeedCursorCodecOption) (*FeedCursorCodec, error) {
	if len(rootSecret) < 32 {
		return nil, fmt.Errorf("feed cursor root secret must contain at least 32 bytes")
	}
	mac := hmac.New(sha256.New, rootSecret)
	_, _ = mac.Write([]byte(feedCursorKeyDerivationDomain))
	key := mac.Sum(nil)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("initialize feed cursor cipher: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("initialize feed cursor AEAD: %w", err)
	}
	codec := &FeedCursorCodec{
		aead:     aead,
		now:      func() time.Time { return time.Now().UTC() },
		ttl:      FeedCursorTTL,
		maxDepth: FeedCursorMaximumDepth,
	}
	for _, opt := range opts {
		if opt == nil {
			continue
		}
		if err := opt(codec); err != nil {
			return nil, err
		}
	}
	return codec, nil
}

func mustNewEphemeralFeedCursorCodec() *FeedCursorCodec {
	root := make([]byte, 32)
	if _, err := cryptorand.Read(root); err != nil {
		panic(fmt.Sprintf("initialize ephemeral feed cursor key: %v", err))
	}
	codec, err := NewFeedCursorCodec(root)
	if err != nil {
		panic(err)
	}
	return codec
}

var defaultFeedCursorCodec = mustNewEphemeralFeedCursorCodec()

func WithFeedCursorCodec(codec *FeedCursorCodec) FeedServiceOption {
	return func(service *FeedService) {
		if codec != nil {
			service.cursorCodec = codec
		}
	}
}

func (codec *FeedCursorCodec) encode(
	state feedCursorEnvelope,
	scope string,
) (string, error) {
	if codec == nil || codec.aead == nil {
		return "", ErrInvalidFeedCursor
	}
	state.Value = strings.TrimSpace(state.Value)
	state.WindowID = strings.TrimSpace(state.WindowID)
	state.AfterContentID = strings.TrimSpace(state.AfterContentID)
	state.DeliveryPageID = strings.TrimSpace(state.DeliveryPageID)
	if !validFeedCursorPayload(state) || state.Depth < 0 || state.Depth > codec.maxDepth {
		return "", ErrInvalidFeedCursor
	}
	if state.ExpiresAt == 0 {
		state.ExpiresAt = codec.now().Add(codec.ttl).UnixMilli()
	}
	raw, err := json.Marshal(state)
	if err != nil {
		return "", fmt.Errorf("encode feed cursor payload: %w", err)
	}
	nonce := make([]byte, codec.aead.NonceSize())
	if _, err := cryptorand.Read(nonce); err != nil {
		return "", fmt.Errorf("generate feed cursor nonce: %w", err)
	}
	sealed := codec.aead.Seal(nonce, nonce, raw, feedCursorAAD(scope))
	return feedCursorPrefix + base64.RawURLEncoding.EncodeToString(sealed), nil
}

func (codec *FeedCursorCodec) decode(
	raw string,
	scope string,
) (feedCursorEnvelope, error) {
	return codec.decodeSealed(raw, scope, false)
}

// decodeSealed validates the complete authenticated cursor envelope. The only
// optional relaxation is the wall-clock expiry check, used when validating the
// service-owned outbound cursor embedded in an immutable delivery-page record:
// an expired outbound continuation must stop forward navigation without making
// the still-valid historical page itself unreadable.
func (codec *FeedCursorCodec) decodeSealed(
	raw string,
	scope string,
	allowExpired bool,
) (feedCursorEnvelope, error) {
	empty := feedCursorEnvelope{}
	raw = strings.TrimSpace(raw)
	if codec == nil || codec.aead == nil || len(raw) > feedCursorMaximumWireBytes ||
		!strings.HasPrefix(raw, feedCursorPrefix) {
		return empty, ErrInvalidFeedCursor
	}
	sealed, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(raw, feedCursorPrefix))
	if err != nil || len(sealed) <= codec.aead.NonceSize() {
		return empty, ErrInvalidFeedCursor
	}
	nonce := sealed[:codec.aead.NonceSize()]
	ciphertext := sealed[codec.aead.NonceSize():]
	plaintext, err := codec.aead.Open(nil, nonce, ciphertext, feedCursorAAD(scope))
	if err != nil {
		return empty, ErrInvalidFeedCursor
	}
	decoder := json.NewDecoder(bytes.NewReader(plaintext))
	decoder.DisallowUnknownFields()
	var state feedCursorEnvelope
	if err := decoder.Decode(&state); err != nil {
		return empty, ErrInvalidFeedCursor
	}
	if err := ensureFeedCursorJSONEOF(decoder); err != nil {
		return empty, ErrInvalidFeedCursor
	}
	state.Value = strings.TrimSpace(state.Value)
	state.WindowID = strings.TrimSpace(state.WindowID)
	state.AfterContentID = strings.TrimSpace(state.AfterContentID)
	state.DeliveryPageID = strings.TrimSpace(state.DeliveryPageID)
	if !validFeedCursorPayload(state) || state.Depth < 0 ||
		state.Depth > codec.maxDepth || state.ExpiresAt <= 0 ||
		(!allowExpired && state.ExpiresAt <= codec.now().UnixMilli()) {
		return empty, ErrInvalidFeedCursor
	}
	return state, nil
}

func ensureFeedCursorJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return ErrInvalidFeedCursor
	}
	return nil
}

func validFeedCursorKind(kind feedCursorKind) bool {
	switch kind {
	case feedCursorKindRecommendation, feedCursorKindPostReader, feedCursorKindDeliveryPage:
		return true
	default:
		return false
	}
}

func validFeedCursorPayload(state feedCursorEnvelope) bool {
	if !validFeedCursorKind(state.Kind) {
		return false
	}
	switch state.Kind {
	case feedCursorKindRecommendation:
		return state.Value == "" && state.WindowID != "" &&
			state.AfterOrdinal > 0 && state.AfterContentID != "" &&
			validDeliveryPageCursorBinding(state)
	case feedCursorKindPostReader:
		return state.Value != "" && state.WindowID == "" &&
			state.AfterOrdinal == 0 && state.AfterContentID == "" &&
			validDeliveryPageCursorBinding(state)
	case feedCursorKindDeliveryPage:
		return state.Value == "" && state.WindowID == "" &&
			state.AfterOrdinal == 0 && state.AfterContentID == "" &&
			state.DeliveryPageID != "" && state.DeliveryPageExpiresAt > 0 &&
			state.ExpiresAt == state.DeliveryPageExpiresAt
	default:
		return false
	}
}

func validDeliveryPageCursorBinding(state feedCursorEnvelope) bool {
	return (state.DeliveryPageID == "" && state.DeliveryPageExpiresAt == 0) ||
		(state.DeliveryPageID != "" && state.DeliveryPageExpiresAt > 0 && state.Depth > 0)
}

func feedCursorAAD(scope string) []byte {
	return []byte(feedCursorKeyDerivationDomain + "\x00" + scope)
}

func feedCursorScope(
	req ListFeedRequest,
	route feedRoute,
	requestedIdentity string,
	requestedType string,
) string {
	values := []string{
		identity.NormalizeAnonymousPersonaID(req.UserID),
		strings.TrimSpace(req.SessionID),
		string(route.FeedType),
		strings.TrimSpace(route.Surface),
		strings.TrimSpace(route.ChannelID),
		strings.TrimSpace(route.Vertical),
		strings.TrimSpace(requestedIdentity),
		strings.TrimSpace(requestedType),
		normalizeFeedSort(req.Sort),
		strconv.Itoa(NormalizeFeedLimit(req.Limit)),
	}
	// Length-prefix every field instead of joining with a sentinel. Request
	// fields are independent strings; delimiter joining is not injective when a
	// value contains that delimiter and could authenticate a cursor under a
	// different actor/session tuple.
	var scope strings.Builder
	for _, value := range values {
		scope.WriteString(strconv.Itoa(len(value)))
		scope.WriteByte(':')
		scope.WriteString(value)
	}
	return scope.String()
}

// EncodePostReaderFeedCursor and DecodePostReaderFeedCursor remain the narrow
// cursor-codec contract helpers used by local contract tests. Production feed
// responses always use the request-scoped codec path in ListFeed.
func EncodePostReaderFeedCursor(postID string, releaseBinding ...string) string {
	releaseID := ""
	manifestDigest := ""
	if len(releaseBinding) >= 2 {
		releaseID = strings.TrimSpace(releaseBinding[0])
		manifestDigest = strings.TrimSpace(releaseBinding[1])
	}
	encoded, err := defaultFeedCursorCodec.encode(feedCursorEnvelope{
		Kind:           feedCursorKindPostReader,
		Value:          strings.TrimSpace(postID),
		ReleaseID:      releaseID,
		ManifestDigest: manifestDigest,
		Depth:          1,
	}, "")
	if err != nil {
		return ""
	}
	return encoded
}

func DecodePostReaderFeedCursor(cursor string) string {
	state, ok := decodePostReaderFeedCursor(cursor)
	if !ok {
		return ""
	}
	return state.PostID
}

func decodePostReaderFeedCursor(cursor string) (postReaderFeedCursorState, bool) {
	state, err := defaultFeedCursorCodec.decode(cursor, "")
	if err != nil || state.Kind != feedCursorKindPostReader {
		return postReaderFeedCursorState{}, false
	}
	return postReaderFeedCursorState{
		PostID:         strings.TrimSpace(state.Value),
		ReleaseID:      strings.TrimSpace(state.ReleaseID),
		ManifestDigest: strings.TrimSpace(state.ManifestDigest),
		Depth:          state.Depth,
	}, true
}

func EncodePostReaderFeedCursorForRequest(
	req ListFeedRequest,
	postID string,
	releaseBinding ...string,
) string {
	req.UserID = identity.NormalizeAnonymousPersonaID(req.UserID)
	requestedIdentity := normalizeRequestedIdentity(req.Identity)
	requestedType := normalizeRequestType(req.Type)
	if strings.TrimSpace(req.ChannelID) != "" {
		requestedIdentity = ""
		requestedType = ""
	}
	route := resolveFeedRoute(req)
	releaseID := ""
	manifestDigest := ""
	if len(releaseBinding) >= 2 {
		releaseID = strings.TrimSpace(releaseBinding[0])
		manifestDigest = strings.TrimSpace(releaseBinding[1])
	}
	encoded, err := defaultFeedCursorCodec.encode(feedCursorEnvelope{
		Kind:           feedCursorKindPostReader,
		Value:          strings.TrimSpace(postID),
		FeedRequestID:  strings.TrimSpace(req.FeedRequestID),
		ReleaseID:      releaseID,
		ManifestDigest: manifestDigest,
		Depth:          1,
	}, feedCursorScope(req, route, requestedIdentity, requestedType))
	if err != nil {
		return ""
	}
	return encoded
}

func feedCursorMatchesActiveRelease(
	state feedCursorEnvelope,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	return activeReleaseID != "" &&
		activeManifestDigest != "" &&
		strings.TrimSpace(state.ReleaseID) == activeReleaseID &&
		strings.TrimSpace(state.ManifestDigest) == activeManifestDigest
}

func releaseBoundCursorValue(releaseBound bool, value string) string {
	if !releaseBound {
		return ""
	}
	return strings.TrimSpace(value)
}
