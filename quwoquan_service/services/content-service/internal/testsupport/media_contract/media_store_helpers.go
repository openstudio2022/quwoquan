package mediacontract

import (
	"time"

	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (s *MediaStore) sessionReceipt(
	key string,
	name string,
	digest string,
) (sessionReceipt, bool, error) {
	receipt, found := s.sessionReceipts[key]
	if !found {
		return sessionReceipt{}, false, nil
	}
	if !receipt.expiry.After(time.Now().UTC()) {
		delete(s.sessionReceipts, key)
		return sessionReceipt{}, false, nil
	}
	if receipt.name != name || receipt.digest != digest {
		return sessionReceipt{}, false, idempotencyConflict()
	}
	return receipt, true, nil
}

func (s *MediaStore) assetReceipt(
	key string,
	name string,
	digest string,
) (assetReceipt, bool, error) {
	receipt, found := s.assetReceipts[key]
	if !found {
		return assetReceipt{}, false, nil
	}
	if !receipt.expiry.After(time.Now().UTC()) {
		delete(s.assetReceipts, key)
		return assetReceipt{}, false, nil
	}
	if receipt.name != name || receipt.digest != digest {
		return assetReceipt{}, false, idempotencyConflict()
	}
	return receipt, true, nil
}

func (s *MediaStore) validateSessionCommit(
	commit mediaports.UploadSessionCommit,
) error {
	if commit.Aggregate == nil ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		commit.IdempotencyKey == "" ||
		len(commit.Events) != 1 {
		return versionConflict()
	}
	current, exists := s.sessions[commit.Aggregate.ID()]
	if commit.ExpectedVersion == 0 {
		if exists {
			return versionConflict()
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return versionConflict()
	}
	event := commit.Events[0]
	if event.AggregateType != "MediaUploadSession" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() {
		return versionConflict()
	}
	return nil
}

func (s *MediaStore) validateAssetCommit(
	commit mediaports.MediaAssetCommit,
) error {
	if commit.Aggregate == nil ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		commit.IdempotencyKey == "" ||
		len(commit.Events) != 1 {
		return versionConflict()
	}
	current, exists := s.assets[commit.Aggregate.ID()]
	if commit.ExpectedVersion == 0 {
		if exists {
			return versionConflict()
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return versionConflict()
	}
	event := commit.Events[0]
	if event.AggregateType != "MediaAsset" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() {
		return versionConflict()
	}
	return nil
}

func (s *MediaStore) validateCompleteCommit(
	commit mediaports.CompleteUploadCommit,
) error {
	if commit.Session == nil ||
		commit.Asset == nil ||
		commit.Session.Version() != commit.ExpectedVersion+1 ||
		commit.Asset.Version() != 1 ||
		commit.Asset.SourceSessionID() != commit.Session.ID() ||
		commit.Asset.OwnerID() != commit.Session.OwnerID() ||
		len(commit.Events) != 2 {
		return versionConflict()
	}
	current, found := s.sessions[commit.Session.ID()]
	if !found || current.Version != commit.ExpectedVersion {
		return versionConflict()
	}
	if _, exists := s.assets[commit.Asset.ID()]; exists {
		return versionConflict()
	}
	hasSession := false
	hasAsset := false
	for _, event := range commit.Events {
		if event.AggregateType == "MediaUploadSession" &&
			event.AggregateID == commit.Session.ID() &&
			event.AggregateVersion == commit.Session.Version() {
			hasSession = true
		}
		if event.AggregateType == "MediaAsset" &&
			event.AggregateID == commit.Asset.ID() &&
			event.AggregateVersion == commit.Asset.Version() {
			hasAsset = true
		}
	}
	if !hasSession || !hasAsset {
		return versionConflict()
	}
	return nil
}

func receiptExpiry(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return value.UTC()
}

func idempotencyConflict() error {
	return contentgenerated.AppErrorFromIdempotencyConflict(
		"test media receipt command mismatch",
	)
}

func versionConflict() error {
	return contentgenerated.AppErrorFromVersionConflict("test media version mismatch")
}

func cloneOutbox(events []mediaports.OutboxEvent) []mediaports.OutboxEvent {
	cloned := make([]mediaports.OutboxEvent, len(events))
	for index, event := range events {
		cloned[index] = event
		cloned[index].Payload = append([]byte(nil), event.Payload...)
	}
	return cloned
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
