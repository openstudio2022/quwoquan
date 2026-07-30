package redis

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"reflect"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"quwoquan_service/runtime/boundedrecord"
	redisruntime "quwoquan_service/runtime/redis"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

type redisReader interface {
	Get(context.Context, string) (string, error)
}

type boundedImmutableRecordAtomicCreator interface {
	CreateBoundedImmutableRecordAtomic(
		context.Context,
		boundedrecord.Request,
	) (boundedrecord.Result, error)
}

type Store struct {
	client      redisReader
	quotaPolicy boundedrecord.Policy
	now         func() time.Time
}

type StoreOption func(*Store)

func WithClock(now func() time.Time) StoreOption {
	return func(store *Store) {
		if now != nil {
			store.now = func() time.Time { return now().UTC() }
		}
	}
}

func WithQuotaPolicy(policy boundedrecord.Policy) StoreOption {
	return func(store *Store) {
		store.quotaPolicy = policy
	}
}

func NewStore(client redisruntime.Client, options ...StoreOption) *Store {
	store := &Store{
		client:      client,
		quotaPolicy: DefaultQuotaPolicy(),
		now:         func() time.Time { return time.Now().UTC() },
	}
	for _, option := range options {
		if option != nil {
			option(store)
		}
	}
	return store
}

var (
	deliveryPageOperations = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "content_feed_delivery_page_total",
		Help: "FeedDeliveryPage append/load outcomes with a bounded result vocabulary.",
	}, []string{"operation", "result"})
	deliveryPagePayloadBytes = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "content_feed_delivery_page_payload_bytes",
		Help:    "Uncompressed FeedDeliveryPage JSON bytes by bounded operation.",
		Buckets: []float64{1024, 4096, 8192, 16384, 32768, deliverymodel.MaximumPayloadBytes},
	}, []string{"operation"})
	deliveryPageQuotaEvictions = promauto.NewCounter(prometheus.CounterOpts{
		Name: "content_feed_delivery_page_quota_evictions_total",
		Help: "FeedDeliveryPage values evicted by the per-scope hard quota.",
	})
	deliveryPageShardLiveRecords = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "content_feed_delivery_page_shard_live_records",
		Help:    "Exact live FeedDeliveryPage records in the touched fixed quota shard.",
		Buckets: []float64{1, 8, 32, 64, 128, 256, 384, 512},
	})
	deliveryPageShardLiveBytes = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "content_feed_delivery_page_shard_live_bytes",
		Help:    "Exact live FeedDeliveryPage payload bytes in the touched fixed quota shard.",
		Buckets: []float64{1 << 20, 4 << 20, 8 << 20, 16 << 20, 24 << 20, 32 << 20},
	})
)

func (s *Store) Append(ctx context.Context, page deliverymodel.Page) (deliverymodel.Page, error) {
	if s == nil || s.client == nil || s.now == nil {
		deliveryPageOperations.WithLabelValues("append", "store_unavailable").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrStoreUnavailable
	}
	if err := s.quotaPolicy.Validate(); err != nil {
		deliveryPageOperations.WithLabelValues("append", "invalid_quota_policy").Inc()
		return deliverymodel.Page{}, fmt.Errorf(
			"%w: invalid quota policy: %v",
			deliveryapp.ErrStoreUnavailable,
			err,
		)
	}
	now := s.now().UTC()
	if err := page.Validate(now); err != nil {
		deliveryPageOperations.WithLabelValues("append", "invalid").Inc()
		return deliverymodel.Page{}, err
	}
	raw, err := json.Marshal(page)
	if err != nil {
		deliveryPageOperations.WithLabelValues("append", "invalid").Inc()
		return deliverymodel.Page{}, fmt.Errorf("encode feed delivery page: %w", err)
	}
	deliveryPagePayloadBytes.WithLabelValues("append").Observe(float64(len(raw)))
	if len(raw) > deliverymodel.MaximumPayloadBytes {
		deliveryPageOperations.WithLabelValues("append", "payload_rejected").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrPayloadTooLarge
	}
	creator, ok := s.client.(boundedImmutableRecordAtomicCreator)
	if !ok {
		deliveryPageOperations.WithLabelValues("append", "atomic_unavailable").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrAtomicUnavailable
	}
	recordKey, indexKey, metadataKey, keyErr := pageQuotaKeys(
		page.ScopeHash,
		page.DeliveryPageID,
		s.quotaPolicy,
	)
	if keyErr != nil {
		deliveryPageOperations.WithLabelValues("append", "invalid").Inc()
		return deliverymodel.Page{}, fmt.Errorf(
			"%w: derive feed delivery page quota keys: %v",
			deliveryapp.ErrStoreUnavailable,
			keyErr,
		)
	}
	admission, err := creator.CreateBoundedImmutableRecordAtomic(
		ctx,
		boundedrecord.Request{
			RecordKey:        recordKey,
			ShardIndexKey:    indexKey,
			ShardMetadataKey: metadataKey,
			OwnerDigest:      page.ScopeHash,
			Value:            string(raw),
			TTL:              page.ExpiresAt.Sub(now),
			Policy:           s.quotaPolicy,
		},
	)
	if err != nil {
		result := "error"
		mapped := error(err)
		switch {
		case errors.Is(err, boundedrecord.ErrShardKeyQuota):
			result = "shard_key_rejected"
			mapped = deliveryapp.ErrShardKeyQuota
		case errors.Is(err, boundedrecord.ErrShardByteQuota):
			result = "shard_byte_rejected"
			mapped = deliveryapp.ErrShardByteQuota
		case errors.Is(err, boundedrecord.ErrRepairBound):
			result = "repair_bound_rejected"
			mapped = deliveryapp.ErrRepairBound
		}
		recordDeliveryPageShardUsage(admission)
		deliveryPageOperations.WithLabelValues("append", result).Inc()
		return deliverymodel.Page{}, fmt.Errorf(
			"%w: append feed delivery page: %w: %v",
			deliveryapp.ErrStoreUnavailable,
			mapped,
			err,
		)
	}
	recordDeliveryPageShardUsage(admission)
	if admission.OwnerEvicted > 0 {
		deliveryPageQuotaEvictions.Add(float64(admission.OwnerEvicted))
	}
	if admission.Created {
		deliveryPageOperations.WithLabelValues("append", "created").Inc()
		return page, nil
	}
	winnerPage, err := decodePage([]byte(admission.Winner), now)
	if err != nil {
		deliveryPageOperations.WithLabelValues("append", "error").Inc()
		return deliverymodel.Page{}, fmt.Errorf("%w: decode feed delivery page winner: %v", deliveryapp.ErrStoreUnavailable, err)
	}
	if !reflect.DeepEqual(winnerPage, page) {
		deliveryPageOperations.WithLabelValues("append", "conflict").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrConflict
	}
	deliveryPageOperations.WithLabelValues("append", "winner").Inc()
	return winnerPage, nil
}

func (s *Store) Load(ctx context.Context, scopeHash, pageID string) (deliverymodel.Page, error) {
	if s == nil || s.client == nil || s.now == nil {
		deliveryPageOperations.WithLabelValues("load", "store_unavailable").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrStoreUnavailable
	}
	if err := s.quotaPolicy.Validate(); err != nil {
		deliveryPageOperations.WithLabelValues("load", "invalid_quota_policy").Inc()
		return deliverymodel.Page{}, fmt.Errorf(
			"%w: invalid quota policy: %v",
			deliveryapp.ErrStoreUnavailable,
			err,
		)
	}
	if !deliverymodel.ValidIdentity(scopeHash, pageID) {
		deliveryPageOperations.WithLabelValues("load", "invalid").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrNotFound
	}
	recordKey, _, _, keyErr := pageQuotaKeys(scopeHash, pageID, s.quotaPolicy)
	if keyErr != nil {
		deliveryPageOperations.WithLabelValues("load", "not_found").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrNotFound
	}
	raw, err := s.client.Get(ctx, recordKey)
	if errors.Is(err, redisruntime.ErrKeyNotFound) || strings.TrimSpace(raw) == "" {
		deliveryPageOperations.WithLabelValues("load", "not_found").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrNotFound
	}
	if err != nil {
		deliveryPageOperations.WithLabelValues("load", "error").Inc()
		return deliverymodel.Page{}, fmt.Errorf("%w: load feed delivery page: %v", deliveryapp.ErrStoreUnavailable, err)
	}
	deliveryPagePayloadBytes.WithLabelValues("load").Observe(float64(len(raw)))
	if len(raw) > deliverymodel.MaximumPayloadBytes {
		deliveryPageOperations.WithLabelValues("load", "payload_rejected").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrPayloadTooLarge
	}
	page, err := decodePage([]byte(raw), s.now())
	if err != nil || page.ScopeHash != strings.TrimSpace(scopeHash) ||
		page.DeliveryPageID != strings.TrimSpace(pageID) {
		deliveryPageOperations.WithLabelValues("load", "invalid").Inc()
		return deliverymodel.Page{}, deliveryapp.ErrNotFound
	}
	deliveryPageOperations.WithLabelValues("load", "success").Inc()
	return page, nil
}

func decodePage(raw []byte, now time.Time) (deliverymodel.Page, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var page deliverymodel.Page
	if err := decoder.Decode(&page); err != nil {
		return deliverymodel.Page{}, err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return deliverymodel.Page{}, errors.New("feed delivery page has trailing payload")
	}
	if err := page.Validate(now); err != nil {
		return deliverymodel.Page{}, err
	}
	return page, nil
}

func DefaultQuotaPolicy() boundedrecord.Policy {
	return boundedrecord.Policy{
		ShardCount:                 256,
		MaximumLiveRecordsPerShard: 512,
		MaximumLiveBytesPerShard:   32 * 1024 * 1024,
		MaximumLiveRecordsPerOwner: deliverymodel.MaximumActivePerScope,
	}
}

func pageKey(scopeHash, pageID string) string {
	key, _, _, _ := pageQuotaKeys(scopeHash, pageID, DefaultQuotaPolicy())
	return key
}

func pageIndexKey(scopeHash string) string {
	_, key, _, _ := pageQuotaShardKeys(scopeHash, DefaultQuotaPolicy())
	return key
}

func pageQuotaKeys(
	scopeHash string,
	pageID string,
	policy boundedrecord.Policy,
) (string, string, string, error) {
	scopeHash = strings.TrimSpace(scopeHash)
	pageID = strings.TrimSpace(pageID)
	if !deliverymodel.ValidIdentity(scopeHash, pageID) {
		return "", "", "", errors.New("feed delivery page quota identity is invalid")
	}
	recordPrefix, indexKey, metadataKey, err := pageQuotaShardKeys(
		scopeHash,
		policy,
	)
	if err != nil {
		return "", "", "", err
	}
	return recordPrefix + ":" + pageID, indexKey, metadataKey, nil
}

func pageQuotaShardKeys(
	scopeHash string,
	policy boundedrecord.Policy,
) (string, string, string, error) {
	scopeHash = strings.TrimSpace(scopeHash)
	if len(scopeHash) != 64 {
		return "", "", "", errors.New("feed delivery page scope digest is invalid")
	}
	shard, err := policy.ShardForDigest(scopeHash)
	if err != nil {
		return "", "", "", err
	}
	hashTag := "{fdp-" + shard + "}"
	return "rec:feed_delivery_page:" + hashTag + ":" + scopeHash,
		"rec:feed_delivery_page_index:" + hashTag,
		"rec:feed_delivery_page_metadata:" + hashTag,
		nil
}

func recordDeliveryPageShardUsage(result boundedrecord.Result) {
	if !result.UsageMeasured {
		return
	}
	deliveryPageShardLiveRecords.Observe(float64(result.LiveRecords))
	deliveryPageShardLiveBytes.Observe(float64(result.LiveBytes))
}
