package mediacontract

import (
	"context"
	"errors"
	"sync"
	"time"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

// MediaStore is test-only durable-store behavior for local contracts. It is
// intentionally outside production composition; production uses MongoMediaStore.
type MediaStore struct {
	mu                     sync.RWMutex
	sessions               map[string]mediamodel.UploadSessionSnapshot
	assets                 map[string]mediamodel.MediaAssetSnapshot
	sessionReceipts        map[string]sessionReceipt
	assetReceipts          map[string]assetReceipt
	originalAccessReceipts map[string]originalAccessReceipt
	outbox                 []mediaports.OutboxEvent
}

type sessionReceipt struct {
	name    string
	digest  string
	session mediamodel.UploadSessionSnapshot
	asset   *mediamodel.MediaAssetSnapshot
	expiry  time.Time
}

type assetReceipt struct {
	name   string
	digest string
	asset  mediamodel.MediaAssetSnapshot
	expiry time.Time
}

type originalAccessReceipt struct {
	digest string
	fact   mediamodel.MediaOriginalAccessFact
}

func NewMediaStore() *MediaStore {
	return &MediaStore{
		sessions:               map[string]mediamodel.UploadSessionSnapshot{},
		assets:                 map[string]mediamodel.MediaAssetSnapshot{},
		sessionReceipts:        map[string]sessionReceipt{},
		assetReceipts:          map[string]assetReceipt{},
		originalAccessReceipts: map[string]originalAccessReceipt{},
	}
}

func (s *MediaStore) AppendMediaOriginalAccess(
	_ context.Context,
	request mediaports.MediaOriginalAccessAppendRequest,
) (mediaports.MediaOriginalAccessAppendResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := request.Fact.Validate(); err != nil {
		return mediaports.MediaOriginalAccessAppendResult{}, err
	}
	if request.Fact.Outcome == "granted" && !request.RateLimit.IsValid() {
		return mediaports.MediaOriginalAccessAppendResult{}, errors.New(
			"media original access append requires a valid rate limit policy",
		)
	}
	if receipt, found := s.originalAccessReceipts[request.Fact.IdempotencyKey]; found {
		if receipt.digest != request.CommandDigest {
			return mediaports.MediaOriginalAccessAppendResult{}, idempotencyConflict()
		}
		return mediaports.MediaOriginalAccessAppendResult{Fact: receipt.fact, Replayed: true}, nil
	}
	if request.Fact.Outcome == "granted" {
		grants := 0
		windowStart := request.Fact.GrantedAt.UTC().Truncate(request.RateLimit.Window)
		for _, receipt := range s.originalAccessReceipts {
			fact := receipt.fact
			if fact.Outcome == "granted" &&
				fact.AssetID == request.Fact.AssetID &&
				fact.ViewerID == request.Fact.ViewerID &&
				fact.Purpose == request.Fact.Purpose &&
				fact.GrantedAt.UTC().Truncate(request.RateLimit.Window).Equal(windowStart) {
				grants++
			}
		}
		if grants >= request.RateLimit.MaxGrants {
			return mediaports.MediaOriginalAccessAppendResult{},
				contentgenerated.AppErrorFromOriginalAccessRateLimited(
					"media original access rate limit exhausted",
				)
		}
	}
	s.originalAccessReceipts[request.Fact.IdempotencyKey] = originalAccessReceipt{
		digest: request.CommandDigest,
		fact:   request.Fact,
	}
	return mediaports.MediaOriginalAccessAppendResult{Fact: request.Fact}, nil
}

func (s *MediaStore) OriginalAccessFacts() []mediamodel.MediaOriginalAccessFact {
	s.mu.RLock()
	defer s.mu.RUnlock()
	facts := make([]mediamodel.MediaOriginalAccessFact, 0, len(s.originalAccessReceipts))
	for _, receipt := range s.originalAccessReceipts {
		facts = append(facts, receipt.fact)
	}
	return facts
}

func (s *MediaStore) LoadUploadSession(
	_ context.Context,
	id string,
) (*mediamodel.MediaUploadSession, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.sessions[id]
	if !ok {
		return nil, false, nil
	}
	aggregate, err := mediamodel.RestoreUploadSession(snapshot)
	return aggregate, err == nil, err
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

func (s *MediaStore) FindUploadSessionForOwner(
	_ context.Context,
	id string,
	ownerID string,
) (mediaapp.MediaUploadSessionSlice, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.sessions[id]
	if !ok || snapshot.OwnerID != ownerID {
		return mediaapp.MediaUploadSessionSlice{}, false, nil
	}
	return mediaapp.MediaUploadSessionSlice{
		SessionID: snapshot.ID, Version: snapshot.Version, ObjectKey: snapshot.ObjectKey,
		MediaType: snapshot.MediaType, ContentType: snapshot.ContentType, FileSize: snapshot.FileSize,
		Status: snapshot.Status, CreatedAt: snapshot.CreatedAt, UpdatedAt: snapshot.UpdatedAt, ExpiresAt: snapshot.ExpiresAt,
	}, true, nil
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
		MediaType:        snapshot.MediaType,
		ContentType:      snapshot.ContentType,
		FileSize:         snapshot.FileSize,
		AccessPolicy:     snapshot.AccessPolicy,
		ProcessingStatus: snapshot.ProcessingStatus,
		CreatedAt:        snapshot.CreatedAt,
		UpdatedAt:        snapshot.UpdatedAt,
		ProcessedAt:      cloneTime(snapshot.ProcessedAt),
		CoverStrategy:    snapshot.CoverStrategy, ManualCoverAssetID: snapshot.ManualCoverAssetID,
		CoverFrameTimeMs: snapshot.CoverFrameTimeMs,
	}, true, nil
}

func (s *MediaStore) FindMediaAssetForOriginalAccess(
	_ context.Context,
	id string,
) (mediaapp.MediaAssetSlice, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, ok := s.assets[id]
	if !ok {
		return mediaapp.MediaAssetSlice{}, false, nil
	}
	return mediaapp.MediaAssetSlice{
		AssetID: snapshot.ID, Version: snapshot.Version, OwnerID: snapshot.OwnerID,
		SourceSessionID: snapshot.SourceSessionID, ObjectKey: snapshot.ObjectKey,
		SHA256: snapshot.SHA256, MediaType: snapshot.MediaType,
		ContentType: snapshot.ContentType, FileSize: snapshot.FileSize,
		AccessPolicy: snapshot.AccessPolicy, ProcessingStatus: snapshot.ProcessingStatus,
		CreatedAt: snapshot.CreatedAt, UpdatedAt: snapshot.UpdatedAt,
		ProcessedAt: cloneTime(snapshot.ProcessedAt),
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
		MediaType: snapshot.MediaType, ContentType: snapshot.ContentType, FileSize: snapshot.FileSize,
		AccessPolicy: snapshot.AccessPolicy, ProcessingStatus: snapshot.ProcessingStatus,
		CreatedAt: snapshot.CreatedAt, UpdatedAt: snapshot.UpdatedAt, ProcessedAt: cloneTime(snapshot.ProcessedAt),
		CoverStrategy: snapshot.CoverStrategy, ManualCoverAssetID: snapshot.ManualCoverAssetID,
		CoverFrameTimeMs: snapshot.CoverFrameTimeMs,
	}, true, nil
}

func (s *MediaStore) FindUploadSessionReceipt(
	_ context.Context,
	key string,
	name string,
	digest string,
) (mediaports.UploadSessionCommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, ok, err := s.sessionReceipt(key, name, digest)
	if err != nil || !ok {
		return mediaports.UploadSessionCommitResult{}, ok, err
	}
	aggregate, err := mediamodel.RestoreUploadSession(receipt.session)
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, false, err
	}
	return mediaports.UploadSessionCommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MediaStore) FindCompleteUploadReceipt(
	_ context.Context,
	key string,
	name string,
	digest string,
) (mediaports.CompleteUploadResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, ok, err := s.sessionReceipt(key, name, digest)
	if err != nil || !ok {
		return mediaports.CompleteUploadResult{}, ok, err
	}
	if receipt.asset == nil {
		return mediaports.CompleteUploadResult{}, false, idempotencyConflict()
	}
	session, err := mediamodel.RestoreUploadSession(receipt.session)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	asset, err := mediamodel.RestoreMediaAsset(*receipt.asset)
	if err != nil {
		return mediaports.CompleteUploadResult{}, false, err
	}
	return mediaports.CompleteUploadResult{Session: session, Asset: asset, Replayed: true}, true, nil
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

func (s *MediaStore) CommitUploadSession(
	_ context.Context,
	commit mediaports.UploadSessionCommit,
) (mediaports.UploadSessionCommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.sessionReceipt(
		commit.IdempotencyKey,
		commit.CommandName,
		commit.CommandDigest,
	)
	if err != nil {
		return mediaports.UploadSessionCommitResult{}, err
	}
	if found {
		aggregate, restoreErr := mediamodel.RestoreUploadSession(receipt.session)
		return mediaports.UploadSessionCommitResult{Aggregate: aggregate, Replayed: true}, restoreErr
	}
	if err := s.validateSessionCommit(commit); err != nil {
		return mediaports.UploadSessionCommitResult{}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	s.sessions[snapshot.ID] = snapshot
	s.sessionReceipts[commit.IdempotencyKey] = sessionReceipt{
		name:    commit.CommandName,
		digest:  commit.CommandDigest,
		session: snapshot,
		expiry:  receiptExpiry(commit.ReceiptExpiresAt),
	}
	s.outbox = append(s.outbox, cloneOutbox(commit.Events)...)
	aggregate, err := mediamodel.RestoreUploadSession(snapshot)
	return mediaports.UploadSessionCommitResult{Aggregate: aggregate}, err
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

func (s *MediaStore) CompleteUpload(
	_ context.Context,
	commit mediaports.CompleteUploadCommit,
) (mediaports.CompleteUploadResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found, err := s.sessionReceipt(
		commit.IdempotencyKey,
		commit.CommandName,
		commit.CommandDigest,
	)
	if err != nil {
		return mediaports.CompleteUploadResult{}, err
	}
	if found {
		if receipt.asset == nil {
			return mediaports.CompleteUploadResult{}, idempotencyConflict()
		}
		session, sessionErr := mediamodel.RestoreUploadSession(receipt.session)
		asset, assetErr := mediamodel.RestoreMediaAsset(*receipt.asset)
		if sessionErr != nil {
			return mediaports.CompleteUploadResult{}, sessionErr
		}
		return mediaports.CompleteUploadResult{
			Session: session, Asset: asset, Replayed: true,
		}, assetErr
	}
	if err := s.validateCompleteCommit(commit); err != nil {
		return mediaports.CompleteUploadResult{}, err
	}
	sessionSnapshot := commit.Session.Snapshot()
	assetSnapshot := commit.Asset.Snapshot()
	s.sessions[sessionSnapshot.ID] = sessionSnapshot
	s.assets[assetSnapshot.ID] = assetSnapshot
	s.sessionReceipts[commit.IdempotencyKey] = sessionReceipt{
		name:    commit.CommandName,
		digest:  commit.CommandDigest,
		session: sessionSnapshot,
		asset:   &assetSnapshot,
		expiry:  receiptExpiry(commit.ReceiptExpiresAt),
	}
	s.assetReceipts[commit.IdempotencyKey] = assetReceipt{
		name:   commit.CommandName,
		digest: commit.CommandDigest,
		asset:  assetSnapshot,
		expiry: receiptExpiry(commit.ReceiptExpiresAt),
	}
	s.outbox = append(s.outbox, cloneOutbox(commit.Events)...)
	session, sessionErr := mediamodel.RestoreUploadSession(sessionSnapshot)
	asset, assetErr := mediamodel.RestoreMediaAsset(assetSnapshot)
	if sessionErr != nil {
		return mediaports.CompleteUploadResult{}, sessionErr
	}
	return mediaports.CompleteUploadResult{Session: session, Asset: asset}, assetErr
}

func (s *MediaStore) OutboxEvents() []mediaports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneOutbox(s.outbox)
}
