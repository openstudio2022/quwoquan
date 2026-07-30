package recommendation

import (
	"bytes"
	"context"
	cryptorand "crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/boundedrecord"
)

const (
	RankedFeedWindowTTL                 = 10 * time.Minute
	RankedFeedWindowMaxItems            = 300
	RankedFeedWindowMaxPayloadBytes     = 2 * 1024 * 1024
	RankedFeedWindowMaxActivePerSubject = 8
	RankedFeedWindowDefaultPageDepth    = 8
	rankedFeedWindowKeyPrefix           = "rec:ranked_feed_window:"
	rankedFeedWindowIndexKeyPrefix      = "rec:ranked_feed_window_index:"
	rankedFeedWindowMetadataKeyPrefix   = "rec:ranked_feed_window_metadata:"
)

var (
	ErrRankedFeedWindowNotFound          = errors.New("ranked feed window not found or expired")
	ErrRankedFeedWindowBindingMismatch   = errors.New("ranked feed window binding mismatch")
	ErrRankedFeedWindowAnchorMismatch    = errors.New("ranked feed window continuation anchor mismatch")
	ErrRankedFeedWindowInvalid           = errors.New("ranked feed window is invalid")
	ErrRankedFeedWindowStoreUnavailable  = errors.New("ranked feed window store unavailable")
	ErrRankedFeedWindowPayloadTooLarge   = errors.New("ranked feed window payload exceeds hard limit")
	ErrRankedFeedWindowEntryBudget       = errors.New("ranked feed window entry exceeds canonical field budget")
	ErrRankedFeedWindowAtomicUnavailable = errors.New(
		"ranked feed window atomic Redis capability unavailable",
	)
)

// rankedFeedWindowAtomicCreator is an optional Redis capability. Production
// adapters must execute the window write, active-window index maintenance,
// expired-member cleanup and oldest-window eviction in one same-slot Redis
// operation. A plain SetNX implementation is deliberately insufficient: it
// cannot enforce the per-subject hard bound under concurrency.
type rankedFeedWindowAtomicCreator interface {
	CreateBoundedImmutableRecordAtomic(
		ctx context.Context,
		request boundedrecord.Request,
	) (boundedrecord.Result, error)
}

// RankedFeedContinuation is the recommendation-owned continuation state sealed
// by content-service's outer AEAD cursor. It deliberately contains no offset or
// live score: continuation is valid only against the immutable Redis window.
type RankedFeedContinuation struct {
	WindowID       string
	AfterOrdinal   int
	AfterContentID string
	ExpiresAt      time.Time
}

type rankedFeedWindowBinding struct {
	// SubjectHash is the privacy-safe digest used in Redis storage/quota keys. It
	// is actor-scoped for named/verified-device traffic and session-scoped for
	// identity-less public traffic. The raw namespaced quota subject is not used
	// as a Redis key; actor/session remain explicit continuation bindings in the
	// stored window payload below.
	SubjectHash    string   `json:"subjectHash"`
	ActorID        string   `json:"actorId"`
	PersonaID      string   `json:"personaId,omitempty"`
	SessionID      string   `json:"sessionId"`
	FeedType       FeedType `json:"feedType"`
	Sort           string   `json:"sort"`
	Surface        string   `json:"surface,omitempty"`
	ChannelID      string   `json:"channelId,omitempty"`
	Vertical       string   `json:"vertical,omitempty"`
	FeedRequestID  string   `json:"feedRequestId"`
	ReleaseID      string   `json:"releaseId,omitempty"`
	ManifestDigest string   `json:"manifestDigest,omitempty"`
}

type rankedFeedWindowProvenance struct {
	CandidateWatermark string `json:"candidateWatermark"`
	PolicyDigest       string `json:"policyDigest"`
	ModelReleaseID     string `json:"modelReleaseId,omitempty"`
	FeatureSnapshotAt  string `json:"featureSnapshotAt"`
	ScorerPath         string `json:"scorerPath"`
}

type rankedFeedTrainingSnapshot struct {
	UserFeatures map[string]any `json:"userFeatures"`
	ItemFeatures map[string]any `json:"itemFeatures"`
	CapturedAt   time.Time      `json:"capturedAt"`
}

type rankedFeedWindowItem struct {
	Ordinal         int                        `json:"ordinal"`
	Item            FeedItem                   `json:"item"`
	SourceOwner     string                     `json:"sourceOwner,omitempty"`
	ReleaseID       string                     `json:"releaseId,omitempty"`
	ManifestDigest  string                     `json:"manifestDigest,omitempty"`
	LifecycleStatus string                     `json:"lifecycleStatus,omitempty"`
	Training        rankedFeedTrainingSnapshot `json:"training"`
}

type rankedFeedWindow struct {
	WindowID        string                     `json:"windowId"`
	CreatedAt       time.Time                  `json:"createdAt"`
	ExpiresAt       time.Time                  `json:"expiresAt"`
	Binding         rankedFeedWindowBinding    `json:"binding"`
	Provenance      rankedFeedWindowProvenance `json:"provenance"`
	Items           []rankedFeedWindowItem     `json:"items"`
	Attribution     DeliveryAttribution        `json:"attribution"`
	TerminalOutcome FeedTerminalOutcome        `json:"terminalOutcome"`
	FailureStage    FailureStage               `json:"failureStage"`
}

// RankedFeedWindowStore is implemented by the existing recommendation Redis
// scene. Create must atomically combine SET NX with the subject quota; Load
// receives the raw, private quota subject and must never extend the key TTL.
type RankedFeedWindowStore interface {
	Create(ctx context.Context, window rankedFeedWindow) (rankedFeedWindow, error)
	Load(ctx context.Context, subjectID, windowID string) (rankedFeedWindow, error)
}

type redisRankedFeedWindowStore struct {
	redis       RedisClient
	quotaPolicy boundedrecord.Policy
	now         func() time.Time
	newWindowID func() (string, error)
}

func NewRedisRankedFeedWindowStore(
	redis RedisClient,
	quotaPolicy boundedrecord.Policy,
) RankedFeedWindowStore {
	return &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: quotaPolicy,
		now:         func() time.Time { return time.Now().UTC() },
		newWindowID: newRankedFeedWindowID,
	}
}

func (s *redisRankedFeedWindowStore) Create(
	ctx context.Context,
	window rankedFeedWindow,
) (rankedFeedWindow, error) {
	if s == nil || s.redis == nil || s.now == nil || s.newWindowID == nil {
		return rankedFeedWindow{}, fmt.Errorf("%w: Redis store is unavailable", ErrRankedFeedWindowInvalid)
	}
	if err := s.quotaPolicy.Validate(); err != nil {
		return rankedFeedWindow{}, fmt.Errorf(
			"%w: quota policy: %v",
			ErrRankedFeedWindowInvalid,
			err,
		)
	}
	createdAt := s.now().UTC()
	window.CreatedAt = createdAt
	window.ExpiresAt = createdAt.Add(RankedFeedWindowTTL)
	windowID, err := s.newWindowID()
	if err != nil {
		return rankedFeedWindow{}, fmt.Errorf("generate ranked feed window id: %w", err)
	}
	window.WindowID = windowID
	if err := validateRankedFeedWindow(window, createdAt); err != nil {
		return rankedFeedWindow{}, err
	}
	encoded, measuredBytes, err := marshalRankedFeedWindowWithinBudget(
		window,
		RankedFeedWindowMaxPayloadBytes,
	)
	recordRankedFeedWindowPayload("create", measuredBytes)
	if err != nil {
		if !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
			recordRankedFeedWindowCreate("error")
			return rankedFeedWindow{}, fmt.Errorf("encode ranked feed window: %w", err)
		}
		recordRankedFeedWindowCreate("payload_rejected")
		return rankedFeedWindow{}, err
	}
	atomicCreator, ok := s.redis.(rankedFeedWindowAtomicCreator)
	if !ok {
		recordRankedFeedWindowCreate("atomic_unavailable")
		return rankedFeedWindow{}, fmt.Errorf(
			"%w: %w",
			ErrRankedFeedWindowStoreUnavailable,
			ErrRankedFeedWindowAtomicUnavailable,
		)
	}
	windowKey, indexKey, metadataKey, err := rankedFeedWindowQuotaKeys(
		window.Binding.SubjectHash,
		window.WindowID,
		s.quotaPolicy,
	)
	if err != nil {
		recordRankedFeedWindowCreate("error")
		return rankedFeedWindow{}, fmt.Errorf(
			"%w: quota keys: %v",
			ErrRankedFeedWindowInvalid,
			err,
		)
	}
	admission, err := atomicCreator.CreateBoundedImmutableRecordAtomic(
		ctx,
		boundedrecord.Request{
			RecordKey:        windowKey,
			ShardIndexKey:    indexKey,
			ShardMetadataKey: metadataKey,
			OwnerDigest:      window.Binding.SubjectHash,
			Value:            string(encoded),
			TTL:              RankedFeedWindowTTL,
			Policy:           s.quotaPolicy,
		},
	)
	if err != nil {
		result := "error"
		switch {
		case errors.Is(err, ErrRankedFeedWindowAtomicUnavailable):
			result = "atomic_unavailable"
		case errors.Is(err, boundedrecord.ErrShardKeyQuota):
			result = "shard_key_rejected"
		case errors.Is(err, boundedrecord.ErrShardByteQuota):
			result = "shard_byte_rejected"
		case errors.Is(err, boundedrecord.ErrRepairBound):
			result = "repair_bound_rejected"
		}
		recordRankedFeedWindowShardUsage(admission)
		recordRankedFeedWindowCreate(result)
		return rankedFeedWindow{}, fmt.Errorf("%w: persist ranked feed window: %w", ErrRankedFeedWindowStoreUnavailable, err)
	}
	recordRankedFeedWindowQuotaEvictions(admission.OwnerEvicted)
	recordRankedFeedWindowShardUsage(admission)
	if admission.Created {
		recordRankedFeedWindowCreate("created")
		return window, nil
	}
	// An atomic-create loser must return the winner actually persisted under the
	// contested ID. Returning the loser's local value would mint a cursor to a
	// window that does not exist; choosing a second ID would hide an ID collision.
	winner, err := decodeRankedFeedWindow(
		admission.Winner,
		window.Binding.SubjectHash,
		window.WindowID,
		s.now().UTC(),
	)
	if err != nil {
		recordRankedFeedWindowCreate("error")
		return rankedFeedWindow{}, fmt.Errorf("%w: decode ranked feed window atomic-create winner: %w", ErrRankedFeedWindowStoreUnavailable, err)
	}
	if !sameRankedFeedWindowContent(winner, window) {
		recordRankedFeedWindowCreate("error")
		return rankedFeedWindow{}, fmt.Errorf("%w: atomic-create winner differs from contender", ErrRankedFeedWindowBindingMismatch)
	}
	recordRankedFeedWindowCreate("winner")
	return winner, nil
}

func (s *redisRankedFeedWindowStore) Load(
	ctx context.Context,
	subjectID string,
	windowID string,
) (rankedFeedWindow, error) {
	if s == nil || s.redis == nil || s.now == nil {
		return rankedFeedWindow{}, fmt.Errorf("load ranked feed window: Redis store is unavailable")
	}
	subjectID = strings.TrimSpace(subjectID)
	windowID = strings.TrimSpace(windowID)
	if subjectID == "" || windowID == "" {
		return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
	}
	subjectHash := rankedFeedWindowSubjectHash(subjectID)
	windowKey, _, _, keyErr := rankedFeedWindowQuotaKeys(
		subjectHash,
		windowID,
		s.quotaPolicy,
	)
	if keyErr != nil {
		return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
	}
	raw, err := s.redis.Get(ctx, windowKey)
	if err != nil {
		if presence, ok := s.redis.(RedisKeyPresenceReader); ok {
			exists, presenceErr := presence.HasKey(ctx, windowKey)
			if presenceErr == nil && !exists {
				return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
			}
		}
		return rankedFeedWindow{}, fmt.Errorf("%w: read ranked feed window: %v", ErrRankedFeedWindowStoreUnavailable, err)
	}
	if strings.TrimSpace(raw) == "" {
		return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
	}
	recordRankedFeedWindowPayload("load", len(raw))
	return decodeRankedFeedWindow(raw, subjectHash, windowID, s.now().UTC())
}

func decodeRankedFeedWindow(
	raw string,
	subjectHash string,
	windowID string,
	now time.Time,
) (rankedFeedWindow, error) {
	if strings.TrimSpace(raw) == "" {
		return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
	}
	if err := validateRankedFeedWindowPayloadSize(len(raw)); err != nil {
		return rankedFeedWindow{}, err
	}
	decoder := json.NewDecoder(bytes.NewBufferString(raw))
	decoder.DisallowUnknownFields()
	var window rankedFeedWindow
	if err := decoder.Decode(&window); err != nil {
		return rankedFeedWindow{}, fmt.Errorf("%w: decode ranked feed window: %v", ErrRankedFeedWindowStoreUnavailable, err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return rankedFeedWindow{}, fmt.Errorf("%w: decode ranked feed window: trailing payload", ErrRankedFeedWindowStoreUnavailable)
	}
	if !window.ExpiresAt.After(now) {
		return rankedFeedWindow{}, ErrRankedFeedWindowNotFound
	}
	if err := validateRankedFeedWindow(window, now); err != nil {
		return rankedFeedWindow{}, err
	}
	if window.WindowID != windowID || window.Binding.SubjectHash != subjectHash {
		return rankedFeedWindow{}, ErrRankedFeedWindowBindingMismatch
	}
	return window, nil
}

func validateRankedFeedWindowPayloadSize(size int) error {
	return validateRankedFeedWindowPayloadSizeWithin(
		size,
		RankedFeedWindowMaxPayloadBytes,
	)
}

func validateRankedFeedWindowPayloadSizeWithin(size, maxBytes int) error {
	if maxBytes > 0 && size <= maxBytes {
		return nil
	}
	return fmt.Errorf(
		"%w: bytes=%d max=%d",
		ErrRankedFeedWindowPayloadTooLarge,
		size,
		maxBytes,
	)
}

// marshalRankedFeedWindowWithinBudget encodes the immutable window without
// first materializing one unbounded whole-window JSON buffer. Top-level fields
// and items are encoded as individual chunks; every append reserves the exact
// remaining envelope bytes and stops before the output buffer can cross the
// budget. The item count is already bounded by validateRankedFeedWindow, and
// this incremental boundary avoids multiplying a large item profile across an
// entire 300-item window before rejecting it.
//
// Entry admission enforces the canonical title/ref-count budgets and the fixed
// model-feature map shape. The owning contracts do not yet declare per-field
// string-byte limits for IDs or refs, so we do not invent them here. Before any
// JSON chunk is allocated, a zero-copy scan proves that the escaped contribution
// of all strings can fit inside the canonical whole-window byte envelope.
func marshalRankedFeedWindowWithinBudget(
	window rankedFeedWindow,
	maxBytes int,
) ([]byte, int, error) {
	if maxBytes <= 0 {
		return nil, 0, fmt.Errorf("ranked feed window payload budget must be positive")
	}
	if err := validateRankedFeedWindowStringEnvelope(window, maxBytes); err != nil {
		return nil, maxBytes + 1, err
	}
	marshalField := func(name string, value any, leadingComma bool) ([]byte, error) {
		valueJSON, err := json.Marshal(value)
		if err != nil {
			return nil, err
		}
		field := make([]byte, 0, len(name)+len(valueJSON)+4)
		if leadingComma {
			field = append(field, ',')
		}
		field = append(field, '"')
		field = append(field, name...)
		field = append(field, '"', ':')
		field = append(field, valueJSON...)
		return field, nil
	}
	appendWithinBudget := func(
		destination []byte,
		chunk []byte,
		reservedBytes int,
	) ([]byte, int, error) {
		projectedBytes := len(destination) + len(chunk) + reservedBytes
		if err := validateRankedFeedWindowPayloadSizeWithin(projectedBytes, maxBytes); err != nil {
			return destination, projectedBytes, err
		}
		return append(destination, chunk...), projectedBytes, nil
	}

	// Build the bounded suffix first so each item append can reserve its exact
	// bytes instead of discovering an overflow only after the items array.
	suffix := []byte{']'}
	for _, field := range []struct {
		name  string
		value any
	}{
		{name: "attribution", value: window.Attribution},
		{name: "terminalOutcome", value: window.TerminalOutcome},
		{name: "failureStage", value: window.FailureStage},
	} {
		fieldJSON, err := marshalField(field.name, field.value, true)
		if err != nil {
			return nil, len(suffix), fmt.Errorf("encode ranked feed window %s: %w", field.name, err)
		}
		var measuredBytes int
		suffix, measuredBytes, err = appendWithinBudget(suffix, fieldJSON, 1)
		if err != nil {
			return nil, measuredBytes, err
		}
	}
	suffix = append(suffix, '}')

	const itemsPrefix = `,"items":[`
	encoded := []byte{'{'}
	prefixFields := []struct {
		name  string
		value any
	}{
		{name: "windowId", value: window.WindowID},
		{name: "createdAt", value: window.CreatedAt},
		{name: "expiresAt", value: window.ExpiresAt},
		{name: "binding", value: window.Binding},
		{name: "provenance", value: window.Provenance},
	}
	for index, field := range prefixFields {
		fieldJSON, err := marshalField(field.name, field.value, index > 0)
		if err != nil {
			return nil, len(encoded), fmt.Errorf("encode ranked feed window %s: %w", field.name, err)
		}
		var measuredBytes int
		encoded, measuredBytes, err = appendWithinBudget(
			encoded,
			fieldJSON,
			len(itemsPrefix)+len(suffix),
		)
		if err != nil {
			return nil, measuredBytes, err
		}
	}
	var measuredBytes int
	var err error
	encoded, measuredBytes, err = appendWithinBudget(encoded, []byte(itemsPrefix), len(suffix))
	if err != nil {
		return nil, measuredBytes, err
	}
	for index, item := range window.Items {
		itemJSON, itemErr := json.Marshal(item)
		if itemErr != nil {
			return nil, len(encoded), fmt.Errorf(
				"encode ranked feed window item ordinal=%d: %w",
				item.Ordinal,
				itemErr,
			)
		}
		separatorBytes := 0
		if index > 0 {
			separatorBytes = 1
		}
		measuredBytes = len(encoded) + separatorBytes + len(itemJSON) + len(suffix)
		if err = validateRankedFeedWindowPayloadSizeWithin(measuredBytes, maxBytes); err != nil {
			return nil, measuredBytes, err
		}
		if separatorBytes > 0 {
			encoded = append(encoded, ',')
		}
		encoded = append(encoded, itemJSON...)
	}
	encoded, measuredBytes, err = appendWithinBudget(encoded, suffix, 0)
	if err != nil {
		return nil, measuredBytes, err
	}
	return encoded, measuredBytes, nil
}

func sameRankedFeedWindowContent(winner, contender rankedFeedWindow) bool {
	contender.CreatedAt = winner.CreatedAt
	contender.ExpiresAt = winner.ExpiresAt
	winnerJSON, _, winnerErr := marshalRankedFeedWindowWithinBudget(
		winner,
		RankedFeedWindowMaxPayloadBytes,
	)
	contenderJSON, _, contenderErr := marshalRankedFeedWindowWithinBudget(
		contender,
		RankedFeedWindowMaxPayloadBytes,
	)
	return winnerErr == nil && contenderErr == nil && bytes.Equal(winnerJSON, contenderJSON)
}

func newRankedFeedWindowID() (string, error) {
	raw := make([]byte, 16)
	if _, err := cryptorand.Read(raw); err != nil {
		return "", err
	}
	return "rfw_" + base64.RawURLEncoding.EncodeToString(raw), nil
}

func rankedFeedWindowKey(subjectID, windowID string) string {
	key, _, _, _ := rankedFeedWindowQuotaKeys(
		rankedFeedWindowSubjectHash(subjectID),
		windowID,
		DefaultRankedFeedWindowQuotaPolicy(),
	)
	return key
}

func rankedFeedWindowIndexKey(subjectID string) string {
	_, key, _, _ := rankedFeedWindowQuotaKeys(
		rankedFeedWindowSubjectHash(subjectID),
		"rfw_index_lookup",
		DefaultRankedFeedWindowQuotaPolicy(),
	)
	return key
}

// DefaultRankedFeedWindowQuotaPolicy is the repository baseline used by tests
// and local composition. Commercial service startup supplies the same fields
// from sys.content-service.feed.ranked_window_* config and rejects zero/invalid
// values rather than silently falling back to this helper.
func DefaultRankedFeedWindowQuotaPolicy() boundedrecord.Policy {
	return boundedrecord.Policy{
		ShardCount:                 256,
		MaximumLiveRecordsPerShard: 128,
		MaximumLiveBytesPerShard:   128 * 1024 * 1024,
		MaximumLiveRecordsPerOwner: RankedFeedWindowMaxActivePerSubject,
	}
}

func rankedFeedWindowQuotaKeys(
	subjectHash string,
	windowID string,
	policy boundedrecord.Policy,
) (string, string, string, error) {
	subjectHash = strings.TrimSpace(subjectHash)
	windowID = strings.TrimSpace(windowID)
	if !validRankedFeedWindowSubjectHash(subjectHash) || windowID == "" {
		return "", "", "", errors.New("ranked feed window quota identity is invalid")
	}
	shard, err := policy.ShardForDigest(subjectHash)
	if err != nil {
		return "", "", "", err
	}
	hashTag := "{rfw-" + shard + "}"
	return rankedFeedWindowKeyPrefix + hashTag + ":" + subjectHash + ":" + windowID,
		rankedFeedWindowIndexKeyPrefix + hashTag,
		rankedFeedWindowMetadataKeyPrefix + hashTag,
		nil
}

func rankedFeedWindowSubjectHash(subjectID string) string {
	subjectID = strings.TrimSpace(subjectID)
	if subjectID == "" {
		return ""
	}
	subjectDigest := sha256.Sum256([]byte(subjectID))
	return hex.EncodeToString(subjectDigest[:16])
}

func validRankedFeedWindowSubjectHash(subjectHash string) bool {
	decoded, err := hex.DecodeString(strings.TrimSpace(subjectHash))
	return err == nil && len(decoded) == 16
}

func validateRankedFeedWindow(window rankedFeedWindow, now time.Time) error {
	if !strings.HasPrefix(strings.TrimSpace(window.WindowID), "rfw_") ||
		window.CreatedAt.IsZero() || window.ExpiresAt.IsZero() ||
		window.ExpiresAt.Sub(window.CreatedAt) != RankedFeedWindowTTL ||
		!window.ExpiresAt.After(now) ||
		!validRankedFeedWindowSubjectHash(window.Binding.SubjectHash) ||
		strings.TrimSpace(window.Binding.ActorID) == "" ||
		strings.TrimSpace(window.Binding.SessionID) == "" ||
		strings.TrimSpace(window.Binding.FeedRequestID) == "" ||
		window.Binding.FeedType == "" ||
		normalizeSort(window.Binding.Sort) != FeedSortRecommend ||
		strings.TrimSpace(window.Provenance.CandidateWatermark) == "" ||
		!validRankedFeedPolicyDigest(window.Provenance.PolicyDigest) ||
		!validRankedFeedFeatureSnapshotAt(window.Provenance.FeatureSnapshotAt) ||
		strings.TrimSpace(window.Provenance.ScorerPath) == "" ||
		window.Attribution.FeedRequestID != window.Binding.FeedRequestID ||
		window.Attribution.PolicyDigest != window.Provenance.PolicyDigest ||
		len(window.Items) == 0 || len(window.Items) > RankedFeedWindowMaxItems {
		return ErrRankedFeedWindowInvalid
	}
	if !validRankedFeedScorerProvenance(window.Provenance) {
		return ErrRankedFeedWindowInvalid
	}
	if (window.Binding.FeedType == FeedDiscovery || window.Binding.FeedType == FeedSimilar) &&
		(strings.TrimSpace(window.Binding.ReleaseID) == "" ||
			strings.TrimSpace(window.Binding.ManifestDigest) == "") {
		return ErrRankedFeedWindowInvalid
	}
	seen := make(map[string]struct{}, len(window.Items))
	for index, entry := range window.Items {
		contentID := strings.TrimSpace(entry.Item.ContentID)
		if entry.Ordinal != index+1 || contentID == "" || entry.Item.rank != 0 ||
			entry.Training.CapturedAt.IsZero() || entry.Training.UserFeatures == nil ||
			entry.Training.ItemFeatures == nil {
			return ErrRankedFeedWindowInvalid
		}
		if _, duplicate := seen[contentID]; duplicate {
			return ErrRankedFeedWindowInvalid
		}
		if err := validateRankedFeedWindowEntryBudget(entry); err != nil {
			return fmt.Errorf("%w: %w: ordinal=%d: %v", ErrRankedFeedWindowInvalid, ErrRankedFeedWindowEntryBudget, entry.Ordinal, err)
		}
		seen[contentID] = struct{}{}
	}
	return nil
}

func validRankedFeedPolicyDigest(value string) bool {
	const prefix = "sha256:"
	if !strings.HasPrefix(value, prefix) {
		return false
	}
	decoded, err := hex.DecodeString(strings.TrimPrefix(value, prefix))
	return err == nil && len(decoded) == sha256.Size
}

func newRankedFeedWindowItem(item FeedItem, ordinal int) (rankedFeedWindowItem, error) {
	if item.trainingFeatures == nil {
		return rankedFeedWindowItem{}, ErrRankedFeedWindowInvalid
	}
	if item.trainingFeatures.validationErr != nil {
		return rankedFeedWindowItem{}, fmt.Errorf(
			"%w: %w: %v",
			ErrRankedFeedWindowInvalid,
			ErrRankedFeedWindowEntryBudget,
			item.trainingFeatures.validationErr,
		)
	}
	wireItem := item
	wireItem.trainingFeatures = nil
	wireItem.rank = 0
	entry := rankedFeedWindowItem{
		Ordinal:         ordinal,
		Item:            wireItem,
		SourceOwner:     item.SourceOwner,
		ReleaseID:       item.ReleaseID,
		ManifestDigest:  item.ManifestDigest,
		LifecycleStatus: item.LifecycleStatus,
		Training: rankedFeedTrainingSnapshot{
			UserFeatures: cloneAnyMap(item.trainingFeatures.userFeatures),
			ItemFeatures: cloneAnyMap(item.trainingFeatures.itemFeatures),
			CapturedAt:   item.trainingFeatures.capturedAt.UTC(),
		},
	}
	if err := validateRankedFeedWindowEntryBudget(entry); err != nil {
		return rankedFeedWindowItem{}, fmt.Errorf("%w: %w: %v", ErrRankedFeedWindowInvalid, ErrRankedFeedWindowEntryBudget, err)
	}
	return entry, nil
}

func (entry rankedFeedWindowItem) feedItem() FeedItem {
	item := entry.Item
	item.SourceOwner = entry.SourceOwner
	item.ReleaseID = entry.ReleaseID
	item.ManifestDigest = entry.ManifestDigest
	item.LifecycleStatus = entry.LifecycleStatus
	item.rank = entry.Ordinal
	item.trainingFeatures = &trainingFeatureSnapshot{
		userFeatures: cloneAnyMap(entry.Training.UserFeatures),
		itemFeatures: cloneAnyMap(entry.Training.ItemFeatures),
		capturedAt:   entry.Training.CapturedAt.UTC(),
	}
	return item
}

func cloneAnyMap(in map[string]any) map[string]any {
	if in == nil {
		return nil
	}
	out := make(map[string]any, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func rankedFeedBindingFromRequest(req GetFeedRequest) rankedFeedWindowBinding {
	return rankedFeedWindowBinding{
		SubjectHash:    rankedFeedWindowSubjectHash(req.RankedWindowSubjectID),
		ActorID:        strings.TrimSpace(req.UserID),
		PersonaID:      strings.TrimSpace(req.PersonaID),
		SessionID:      strings.TrimSpace(req.SessionID),
		FeedType:       req.FeedType,
		Sort:           normalizeSort(req.Sort),
		Surface:        strings.TrimSpace(req.Surface),
		ChannelID:      strings.TrimSpace(req.ChannelID),
		Vertical:       strings.TrimSpace(req.Vertical),
		FeedRequestID:  strings.TrimSpace(req.FeedRequestID),
		ReleaseID:      strings.TrimSpace(req.ActiveReleaseID),
		ManifestDigest: strings.TrimSpace(req.ActiveManifestDigest),
	}
}

func rankedFeedWindowMatchesRequest(window rankedFeedWindow, req GetFeedRequest) bool {
	want := rankedFeedBindingFromRequest(req)
	return window.Binding == want
}

func rankedFeedCandidateWatermark(candidates []ContentCandidate) string {
	lines := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		lines = append(lines, strings.Join([]string{
			strings.TrimSpace(candidate.ContentID),
			strings.TrimSpace(candidate.SourceOwner),
			strings.TrimSpace(candidate.ReleaseID),
			strings.TrimSpace(candidate.ManifestDigest),
			strings.TrimSpace(candidate.LifecycleStatus),
			strings.TrimSpace(candidate.RecallPath),
		}, "\x1f"))
	}
	sort.Strings(lines)
	hash := sha256.New()
	for _, line := range lines {
		_, _ = hash.Write([]byte(fmt.Sprintf("%d:", len(line))))
		_, _ = hash.Write([]byte(line))
	}
	return "sha256:" + hex.EncodeToString(hash.Sum(nil))
}

func validRankedFeedFeatureSnapshotAt(value string) bool {
	_, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(value))
	return err == nil
}

func validRankedFeedScorerProvenance(provenance rankedFeedWindowProvenance) bool {
	switch strings.TrimSpace(provenance.ScorerPath) {
	case "model":
		return strings.TrimSpace(provenance.ModelReleaseID) != ""
	case "rule", "rule_fallback":
		return strings.TrimSpace(provenance.ModelReleaseID) == ""
	default:
		return false
	}
}

func rankedFeedWindowLimit(pageLimit int) int {
	if pageLimit <= 0 {
		pageLimit = 20
	}
	limit := pageLimit * RankedFeedWindowDefaultPageDepth
	if limit > RankedFeedWindowMaxItems {
		return RankedFeedWindowMaxItems
	}
	return limit
}
