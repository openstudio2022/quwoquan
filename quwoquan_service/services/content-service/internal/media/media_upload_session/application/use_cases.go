package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contenterrors "quwoquan_service/services/content-service/generated/content/post"
	asseterrors "quwoquan_service/services/content-service/generated/media/media_asset"
	uploaderrors "quwoquan_service/services/content-service/generated/media/media_upload_session"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaassetapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

type UseCases struct {
	store   ports.Store
	objects ObjectStore
	now     func() time.Time
	newID   func(string) (string, error)
}

type Option func(*UseCases)

func WithClock(now func() time.Time) Option {
	return func(useCases *UseCases) {
		if now != nil {
			useCases.now = now
		}
	}
}

func WithIdentifierGenerator(newID func(string) (string, error)) Option {
	return func(useCases *UseCases) {
		if newID != nil {
			useCases.newID = newID
		}
	}
}

func NewUseCases(store ports.Store, objects ObjectStore, options ...Option) *UseCases {
	if store == nil || objects == nil {
		panic("media upload session requires store and object store")
	}
	useCases := &UseCases{
		store:   store,
		objects: objects,
		now:     time.Now,
		newID:   newIdentifier,
	}
	for _, option := range options {
		option(useCases)
	}
	return useCases
}

type InitCommand struct {
	OwnerID        string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
}

type CompleteCommand struct {
	SessionID    string
	OwnerID      string
	AccessPolicy string
}

type AbortCommand struct {
	SessionID string
	OwnerID   string
}

type GetQuery struct {
	SessionID string
	OwnerID   string
}

type CommandResult struct {
	SessionID             string
	Version               int64
	Status                model.Status
	AssetID               string
	AssetProcessingStatus string
	ObjectKey             string
	UploadURL             string
	ExpiresAt             time.Time
	Replayed              bool
}

type Slice struct {
	SessionID   string       `json:"sessionId"`
	Version     int64        `json:"version"`
	AssetID     string       `json:"assetId,omitempty"`
	MediaType   string       `json:"mediaType"`
	ContentType string       `json:"contentType"`
	FileSize    int64        `json:"fileSize"`
	Status      model.Status `json:"status"`
	CreatedAt   time.Time    `json:"createdAt"`
	UpdatedAt   time.Time    `json:"updatedAt"`
	ExpiresAt   time.Time    `json:"expiresAt"`
}

type PrepareUploadParams struct {
	SessionID      string
	OwnerID        string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
	ExpiresAt      time.Time
}

type UploadGrant struct {
	ObjectKey string
	UploadURL string
	ExpiresAt time.Time
}

type CompleteUploadParams struct {
	ObjectKey      string
	ExpectedSHA256 string
	MediaType      string
	ContentType    string
	FileSize       int64
}

type CompletedObject struct {
	ObjectKey string
	SHA256    string
}

type ObjectStore interface {
	PrepareUpload(context.Context, PrepareUploadParams) (UploadGrant, error)
	UploadURL(context.Context, string, string, string, time.Time) (string, error)
	CompleteUpload(context.Context, CompleteUploadParams) (CompletedObject, error)
	DeleteTemporaryUpload(context.Context, string) error
}

func (s *UseCases) Init(ctx context.Context, command InitCommand) (CommandResult, error) {
	command = normalizeInit(command)
	encoded, err := json.Marshal(command)
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	digest := commandDigest("InitMediaUpload", encoded)
	if replayed, found, err := s.replay(ctx, "InitMediaUpload", digest); err != nil || found {
		return replayed, err
	}
	if err := validateInit(command); err != nil {
		return CommandResult{}, err
	}
	now := s.now().UTC()
	sessionID, err := s.newID("mus")
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	grant, err := s.objects.PrepareUpload(ctx, PrepareUploadParams{
		SessionID: sessionID, OwnerID: command.OwnerID, MediaType: command.MediaType,
		ContentType: command.ContentType, FileSize: command.FileSize,
		ExpectedSHA256: command.ExpectedSHA256, ExpiresAt: now.Add(15 * time.Minute),
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	session, err := model.Create(model.CreateParams{
		ID: sessionID, OwnerID: command.OwnerID, ObjectKey: grant.ObjectKey,
		MediaType: command.MediaType, ContentType: command.ContentType,
		FileSize: command.FileSize, ExpectedSHA256: command.ExpectedSHA256,
		ExpiresAt: grant.ExpiresAt, Now: now,
	})
	if err != nil {
		return CommandResult{}, mapDomainError(err)
	}
	payload, err := json.Marshal(map[string]any{
		"sessionId": session.ID(), "ownerId": session.OwnerID(),
		"objectKey": session.ObjectKey(), "expiresAt": session.ExpiresAt(),
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	result, err := s.commit(ctx, session, 0, "InitMediaUpload", digest, "content.media_upload.initialized", payload, now)
	if err != nil {
		return CommandResult{}, err
	}
	result.ObjectKey = grant.ObjectKey
	result.UploadURL = grant.UploadURL
	result.ExpiresAt = grant.ExpiresAt
	return result, nil
}

func (s *UseCases) Complete(ctx context.Context, command CompleteCommand) (CommandResult, error) {
	command.SessionID = strings.TrimSpace(command.SessionID)
	command.OwnerID = strings.TrimSpace(command.OwnerID)
	command.AccessPolicy = strings.TrimSpace(command.AccessPolicy)
	if command.AccessPolicy == "" {
		command.AccessPolicy = "owner_only"
	}
	encoded, err := json.Marshal(command)
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	digest := commandDigest("CompleteMediaUpload", encoded)
	if replayed, found, err := s.replay(ctx, "CompleteMediaUpload", digest); err != nil || found {
		return replayed, err
	}
	session, found, err := s.store.Load(ctx, strings.TrimSpace(command.SessionID))
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	if !found {
		return CommandResult{}, asseterrors.AppErrorFromMediaNotFound(command.SessionID)
	}
	now := s.now().UTC()
	assetID, err := s.newID("mas")
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	if err := session.Complete(command.OwnerID, session.ExpectedSHA256(), assetID, now); err != nil {
		return CommandResult{}, mapDomainError(err)
	}
	completed, err := s.objects.CompleteUpload(ctx, CompleteUploadParams{
		ObjectKey: session.ObjectKey(), ExpectedSHA256: session.ExpectedSHA256(),
		MediaType: session.MediaType(), ContentType: session.ContentType(), FileSize: session.FileSize(),
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	asset, err := mediaassetapp.BuildUploadCreation(
		mediaassetapp.UploadCreationParams{
			ID:              assetID,
			OwnerID:         session.OwnerID(),
			SourceSessionID: session.ID(),
			ObjectKey:       completed.ObjectKey,
			SHA256:          completed.SHA256,
			MediaType:       session.MediaType(),
			ContentType:     session.ContentType(),
			FileSize:        session.FileSize(),
			AccessPolicy:    command.AccessPolicy,
			Now:             now,
		},
	)
	if err != nil {
		return CommandResult{}, contenterrors.AppErrorFromInvalidArgument(err.Error())
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	assetEventID, err := s.newID("evt")
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	sessionPayload, err := json.Marshal(map[string]any{
		"sessionId": session.ID(), "ownerId": session.OwnerID(),
		"objectKey": session.ObjectKey(), "assetId": assetID,
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	assetPayload, err := json.Marshal(map[string]any{
		"assetId": asset.ID, "ownerId": asset.OwnerID, "sourceSessionId": asset.SourceSessionID,
		"objectKey": asset.ObjectKey, "sha256": asset.SHA256,
		"contentType": asset.ContentType, "fileSize": asset.FileSize,
		"processingStatus": asset.ProcessingStatus,
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	key, err := idempotencyKey(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	receipt, err := s.store.Complete(ctx, ports.CompleteCommit{
		Session: session, ExpectedVersion: session.Version() - 1, Asset: asset,
		IdempotencyKey: key,
		CommandName:    "CompleteMediaUpload", CommandDigest: digest,
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []ports.Event{
			{ID: eventID, Type: "content.media_upload.completed", AggregateType: "MediaUploadSession", AggregateID: session.ID(), AggregateVersion: session.Version(), Payload: sessionPayload, OccurredAt: now},
			{ID: assetEventID, Type: "content.media_asset.created", AggregateType: "MediaAsset", AggregateID: asset.ID, AggregateVersion: asset.Version, Payload: assetPayload, OccurredAt: now},
		},
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	return resultFromReceipt(receipt), nil
}

func (s *UseCases) Abort(ctx context.Context, command AbortCommand) (CommandResult, error) {
	command.SessionID = strings.TrimSpace(command.SessionID)
	command.OwnerID = strings.TrimSpace(command.OwnerID)
	encoded, err := json.Marshal(command)
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	digest := commandDigest("AbortMediaUpload", encoded)
	if replayed, found, err := s.replay(ctx, "AbortMediaUpload", digest); err != nil {
		return replayed, err
	} else if found {
		if err := s.objects.DeleteTemporaryUpload(ctx, replayed.ObjectKey); err != nil {
			return CommandResult{}, unavailable(err)
		}
		return replayed, nil
	}
	session, found, err := s.store.Load(ctx, command.SessionID)
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	if !found {
		return CommandResult{}, asseterrors.AppErrorFromMediaNotFound(command.SessionID)
	}
	now := s.now().UTC()
	expectedVersion := session.Version()
	if err := session.Abort(command.OwnerID, now); err != nil {
		return CommandResult{}, mapDomainError(err)
	}
	payload, err := json.Marshal(map[string]any{"sessionId": session.ID(), "ownerId": session.OwnerID()})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	result, err := s.commit(
		ctx,
		session,
		expectedVersion,
		"AbortMediaUpload",
		digest,
		"content.media_upload.aborted",
		payload,
		now,
	)
	if err != nil {
		return CommandResult{}, err
	}
	if err := s.objects.DeleteTemporaryUpload(ctx, session.ObjectKey()); err != nil {
		return CommandResult{}, unavailable(err)
	}
	return result, nil
}

func (s *UseCases) Get(ctx context.Context, query GetQuery) (Slice, error) {
	snapshot, found, err := s.store.FindForOwner(ctx, strings.TrimSpace(query.SessionID), strings.TrimSpace(query.OwnerID))
	if err != nil {
		return Slice{}, unavailable(err)
	}
	if !found {
		return Slice{}, asseterrors.AppErrorFromMediaNotFound(query.SessionID)
	}
	return Slice{
		SessionID: snapshot.ID, Version: snapshot.Version, AssetID: snapshot.AssetID,
		MediaType: snapshot.MediaType, ContentType: snapshot.ContentType,
		FileSize: snapshot.FileSize, Status: snapshot.Status, CreatedAt: snapshot.CreatedAt,
		UpdatedAt: snapshot.UpdatedAt, ExpiresAt: snapshot.ExpiresAt,
	}, nil
}

func (s *UseCases) replay(ctx context.Context, commandName, digest string) (CommandResult, bool, error) {
	key, err := idempotencyKey(ctx)
	if err != nil {
		return CommandResult{}, false, err
	}
	receipt, found, err := s.store.FindReceipt(ctx, key, commandName, digest)
	if err != nil || !found {
		if err != nil {
			return CommandResult{}, false, unavailable(err)
		}
		return CommandResult{}, false, nil
	}
	result := resultFromReceipt(receipt)
	if commandName == "InitMediaUpload" && result.Status == model.StatusPending {
		if !s.now().UTC().Before(result.ExpiresAt) {
			return result, true, nil
		}
		uploadURL, err := s.objects.UploadURL(ctx, result.ObjectKey, receipt.Session.ContentType(), receipt.Session.ExpectedSHA256(), result.ExpiresAt)
		if err != nil {
			return CommandResult{}, false, unavailable(err)
		}
		result.UploadURL = uploadURL
	}
	return result, true, nil
}

func (s *UseCases) commit(ctx context.Context, session *model.Session, expectedVersion int64, commandName, digest, eventType string, payload []byte, now time.Time) (CommandResult, error) {
	key, err := idempotencyKey(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	receipt, err := s.store.Commit(ctx, ports.Commit{
		Session: session, ExpectedVersion: expectedVersion, IdempotencyKey: key,
		CommandName: commandName, CommandDigest: digest, ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []ports.Event{{ID: eventID, Type: eventType, AggregateType: "MediaUploadSession", AggregateID: session.ID(), AggregateVersion: session.Version(), Payload: payload, OccurredAt: now}},
	})
	if err != nil {
		return CommandResult{}, unavailable(err)
	}
	return resultFromReceipt(receipt), nil
}

func resultFromReceipt(receipt ports.Receipt) CommandResult {
	if receipt.Session == nil {
		return CommandResult{Replayed: receipt.Replayed}
	}
	return CommandResult{
		SessionID: receipt.Session.ID(), Version: receipt.Session.Version(),
		Status: receipt.Session.Status(), AssetID: receipt.Session.AssetID(),
		AssetProcessingStatus: receipt.AssetProcessingStatus,
		ObjectKey:             receipt.Session.ObjectKey(), ExpiresAt: receipt.Session.ExpiresAt(),
		Replayed: receipt.Replayed,
	}
}

func validateInit(command InitCommand) error {
	if command.OwnerID == "" || command.FileSize <= 0 || !validDigest(command.ExpectedSHA256) {
		return contenterrors.AppErrorFromInvalidArgument("media upload requires owner, positive fileSize and SHA-256")
	}
	policy, ok := uploaderrors.ContentMediaUploadPolicies[command.MediaType]
	if !ok || !contentTypeAllowed(policy.AllowedContentTypes, command.ContentType) {
		return uploaderrors.AppErrorFromMediaTypeUnsupported(fmt.Sprintf("mediaType=%q contentType=%q is not allowed", command.MediaType, command.ContentType))
	}
	if command.FileSize > policy.MaxFileSizeBytes {
		return uploaderrors.AppErrorFromMediaFileTooLarge(fmt.Sprintf("media file size %d exceeds maximum %d for %s", command.FileSize, policy.MaxFileSizeBytes, command.MediaType))
	}
	return nil
}

func normalizeInit(command InitCommand) InitCommand {
	command.OwnerID = strings.TrimSpace(command.OwnerID)
	command.MediaType = strings.ToLower(strings.TrimSpace(command.MediaType))
	command.ContentType = strings.ToLower(strings.TrimSpace(strings.Split(command.ContentType, ";")[0]))
	command.ExpectedSHA256 = strings.ToLower(strings.TrimSpace(command.ExpectedSHA256))
	return command
}

func contentTypeAllowed(allowed map[string]struct{}, contentType string) bool {
	if contentType == "" {
		return false
	}
	if _, wildcard := allowed["*/*"]; wildcard {
		return strings.Contains(contentType, "/")
	}
	_, ok := allowed[contentType]
	return ok
}

func validDigest(value string) bool {
	value = strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
	if len(value) != 64 {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func idempotencyKey(ctx context.Context) (string, error) {
	key := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if key == "" {
		return "", rterr.NewInvalidArgument(rterr.ModuleContent, "idempotencyKey 必填", "media command requires idempotencyKey")
	}
	return key, nil
}

func commandDigest(commandName string, encoded []byte) string {
	hash := sha256.New()
	_, _ = hash.Write([]byte(commandName))
	_, _ = hash.Write([]byte{0})
	_, _ = hash.Write(encoded)
	return hex.EncodeToString(hash.Sum(nil))
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrSessionOwnerForbidden):
		return contenterrors.AppErrorFromUnauthorized(err.Error())
	case errors.Is(err, model.ErrSessionExpired):
		return uploaderrors.AppErrorFromMediaUploadSessionExpired(err.Error())
	case errors.Is(err, model.ErrInvalidSession),
		errors.Is(err, model.ErrInvalidSessionTransition),
		errors.Is(err, model.ErrDigestMismatch):
		return rterr.NewInvalidArgument(rterr.ModuleContent, "媒体状态或参数不合法", err.Error())
	default:
		return err
	}
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return rterr.NewUnavailable(rterr.ModuleContent, "媒体服务暂时不可用", err.Error())
}

func newIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}
