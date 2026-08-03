package mediacontract

import (
	"context"
	"errors"
	"sync"
	"time"

	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

// MediaStore is test-only durable-store behavior for local contracts. It is
// intentionally outside production composition; production uses MongoMediaStore.
type MediaStore struct {
	mu            sync.RWMutex
	assets        map[string]mediamodel.MediaAssetSnapshot
	assetReceipts map[string]assetReceipt
	outbox        []mediaports.OutboxEvent
}

type assetReceipt struct {
	name   string
	digest string
	asset  mediamodel.MediaAssetSnapshot
	expiry time.Time
}

func NewMediaStore() *MediaStore {
	return &MediaStore{
		assets:        map[string]mediamodel.MediaAssetSnapshot{},
		assetReceipts: map[string]assetReceipt{},
	}
}

func (s *MediaStore) LoadMediaAsset(
	_ context.Context,
	id string,
) (*mediamodel.MediaAsset, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.assets[id]
	if !ok {
		return nil, false, nil
	}
	aggregate, err := mediamodel.RestoreMediaAsset(snapshot)
	return aggregate, err == nil, err
}

func (s *MediaStore) FindMediaAssetForOwner(
	_ context.Context,
	id string,
	ownerID string,
) (mediaapp.MediaAssetSlice, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.assets[id]
	if !ok || snapshot.OwnerID != ownerID {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	return mediaapp.MediaAssetSlice{
		AssetID:          snapshot.ID,
		Version:          snapshot.Version,
		OwnerID:          snapshot.OwnerID,
		SourceSessionID:  snapshot.SourceSessionID,
		ObjectKey:        snapshot.ObjectKey,
		SHA256:           snapshot.SHA256,
		MediaType:        string(snapshot.MediaType),
		MimeType:         snapshot.MimeType,
		FileSize:         snapshot.FileSize,
		AccessPolicy:     snapshot.AccessPolicy,
		ProcessingStatus: snapshot.ProcessingStatus,
		CreatedAt:        snapshot.CreatedAt,
		UpdatedAt:        snapshot.UpdatedAt,
		ProcessedAt:      cloneTime(snapshot.ProcessedAt),
		CoverStrategy:    string(snapshot.CoverStrategy), ManualCoverAssetID: snapshot.ManualCoverAssetID,
		CoverFrameTimeMs: snapshot.CoverFrameTimeMs,
	}, true, nil
}

func (s *MediaStore) FindPublicMediaAsset(
	_ context.Context,
	id string,
) (mediaapp.MediaAssetSlice, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.assets[id]
	if !ok || snapshot.AccessPolicy != mediamodel.AccessPolicyPublic || snapshot.ProcessingStatus != mediamodel.ProcessingStatusReady {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	return mediaapp.MediaAssetSlice{
		AssetID: snapshot.ID, Version: snapshot.Version, OwnerID: snapshot.OwnerID,
		SourceSessionID: snapshot.SourceSessionID, ObjectKey: snapshot.ObjectKey, SHA256: snapshot.SHA256,
		MediaType: string(snapshot.MediaType), MimeType: snapshot.MimeType, FileSize: snapshot.FileSize,
		AccessPolicy: snapshot.AccessPolicy, ProcessingStatus: snapshot.ProcessingStatus,
		CreatedAt: snapshot.CreatedAt, UpdatedAt: snapshot.UpdatedAt, ProcessedAt: cloneTime(snapshot.ProcessedAt),
		CoverStrategy: string(snapshot.CoverStrategy), ManualCoverAssetID: snapshot.ManualCoverAssetID,
		CoverFrameTimeMs: snapshot.CoverFrameTimeMs,
	}, true, nil
}

func (s *MediaStore) FindMediaAssetReceipt(
	_ context.Context,
	key string,
	name string,
	digest string,
) (mediaports.MediaAssetCommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, ok, err := s.assetReceipt(key, name, digest)
	if err != nil || !ok {
		return mediaports.MediaAssetCommitResult{}, ok, err
	}
	aggregate, err := mediamodel.RestoreMediaAsset(receipt.asset)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, false, err
	}
	return mediaports.MediaAssetCommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MediaStore) RecordMediaAssetNoopReceipt(
	_ context.Context,
	noop mediaports.MediaAssetNoopReceipt,
) (mediaports.MediaAssetCommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.assetReceipt(
		noop.IdempotencyKey,
		noop.CommandName,
		noop.CommandDigest,
	)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	if found {
		aggregate, restoreErr := mediamodel.RestoreMediaAsset(receipt.asset)
		return mediaports.MediaAssetCommitResult{Aggregate: aggregate, Replayed: true}, restoreErr
	}
	if noop.Aggregate == nil {
		return mediaports.MediaAssetCommitResult{}, errors.New(
			"media asset no-op receipt requires aggregate",
		)
	}
	snapshot := noop.Aggregate.Snapshot()
	s.assetReceipts[noop.IdempotencyKey] = assetReceipt{
		name:   noop.CommandName,
		digest: noop.CommandDigest,
		asset:  snapshot,
		expiry: receiptExpiry(noop.ReceiptExpiresAt),
	}
	aggregate, err := mediamodel.RestoreMediaAsset(snapshot)
	return mediaports.MediaAssetCommitResult{Aggregate: aggregate}, err
}

func (s *MediaStore) CommitMediaAsset(
	_ context.Context,
	commit mediaports.MediaAssetCommit,
) (mediaports.MediaAssetCommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.assetReceipt(
		commit.IdempotencyKey,
		commit.CommandName,
		commit.CommandDigest,
	)
	if err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	if found {
		aggregate, restoreErr := mediamodel.RestoreMediaAsset(receipt.asset)
		return mediaports.MediaAssetCommitResult{Aggregate: aggregate, Replayed: true}, restoreErr
	}
	if err := s.validateAssetCommit(commit); err != nil {
		return mediaports.MediaAssetCommitResult{}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	s.assets[snapshot.ID] = snapshot
	s.assetReceipts[commit.IdempotencyKey] = assetReceipt{
		name:   commit.CommandName,
		digest: commit.CommandDigest,
		asset:  snapshot,
		expiry: receiptExpiry(commit.ReceiptExpiresAt),
	}
	s.outbox = append(s.outbox, cloneOutbox(commit.Events)...)
	aggregate, err := mediamodel.RestoreMediaAsset(snapshot)
	return mediaports.MediaAssetCommitResult{Aggregate: aggregate}, err
}

func (s *MediaStore) OutboxEvents() []mediaports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneOutbox(s.outbox)
}
