package circlefile

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	generated "quwoquan_service/services/circle-service/generated/circle_management/circle"
	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	fileports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
)

const fileReceiptRetention = 7 * 24 * time.Hour

type CreateCommand struct {
	CircleID       string
	GroupID        string
	ParentFolderID *string
	Name           string
	FileType       filemodel.CircleFileType
	AssetID        string
}

type UpdateCommand struct {
	CircleID        string
	FileID          string
	ExpectedVersion int64
	ParentFolderID  *string
	Name            *string
}

type DeleteCommand struct {
	CircleID string
	FileID   string
}

type CommandResult struct {
	FileID           string `json:"fileId"`
	Version          int64  `json:"version"`
	Status           string `json:"status"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type CommandFacade struct {
	store       fileports.AggregateStore
	policies    fileports.PolicyReader
	mediaAssets fileports.MediaAssetOwnerReader
	now         func() time.Time
}

func NewCommandFacade(store fileports.AggregateStore, policies fileports.PolicyReader, mediaAssets fileports.MediaAssetOwnerReader) *CommandFacade {
	if store == nil || policies == nil || mediaAssets == nil {
		panic("CircleFile CommandFacade requires Store, named policy Readers and MediaAsset owner Reader")
	}
	return &CommandFacade{store: store, policies: policies, mediaAssets: mediaAssets, now: time.Now}
}

func (facade *CommandFacade) Create(ctx context.Context, command CreateCommand) (CommandResult, error) {
	current, actorID, err := trustedFileCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	policy, err := facade.requireSpaceAccess(ctx, command.CircleID, command.GroupID, actorID, false)
	if err != nil {
		return CommandResult{}, err
	}
	fileID := stableFileID(command.CircleID, actorID, current.IdempotencyKey)
	if err := facade.validateParent(ctx, command.CircleID, command.GroupID, fileID, command.ParentFolderID); err != nil {
		return CommandResult{}, err
	}
	name := command.Name
	change := filemodel.ChangeSet{
		Kind: filemodel.ChangeCreate, FileID: fileID, CircleID: strings.TrimSpace(command.CircleID),
		GroupID: strings.TrimSpace(command.GroupID), ParentFolderID: command.ParentFolderID,
		Name: &name, FileType: command.FileType, UploaderPersonaID: actorID, OccurredAt: facade.now().UTC(),
	}
	if command.FileType == filemodel.CircleFileTypeFile {
		asset, found, readErr := facade.mediaAssets.ReadOwnedReadyAsset(ctx, strings.TrimSpace(command.AssetID), actorID)
		if readErr != nil {
			return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(readErr.Error())
		}
		if !found || asset.OwnerPersonaID != actorID || asset.ProcessingStatus != "ready" || asset.FileSize <= 0 || strings.TrimSpace(asset.ContentType) == "" {
			return CommandResult{}, generated.AppErrorFromFileAssetInvalid("ready owner-scoped MediaAsset is required")
		}
		change.AssetID, change.MimeType, change.SizeBytes = asset.AssetID, asset.ContentType, asset.FileSize
	} else if strings.TrimSpace(command.AssetID) != "" {
		return CommandResult{}, generated.AppErrorFromFileAssetInvalid("folder cannot bind MediaAsset")
	}
	return facade.commit(ctx, current, actorID, change, policy.QuotaBytes)
}

func (facade *CommandFacade) Update(ctx context.Context, command UpdateCommand) (CommandResult, error) {
	current, actorID, err := trustedFileCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	file, found, err := facade.store.Load(ctx, strings.TrimSpace(command.FileID))
	if err != nil {
		return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || file.CircleID != strings.TrimSpace(command.CircleID) {
		return CommandResult{}, generated.AppErrorFromFileNotFound("CircleFile not found in Circle")
	}
	policy, err := facade.requireSpaceAccess(ctx, file.CircleID, file.GroupID, actorID, file.UploaderPersonaID != actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if command.ExpectedVersion <= 0 {
		return CommandResult{}, generated.AppErrorFromInvalidArgument("If-Match version is required")
	}
	if err := facade.validateParent(ctx, file.CircleID, file.GroupID, file.ID, command.ParentFolderID); err != nil {
		return CommandResult{}, err
	}
	return facade.commit(ctx, current, actorID, filemodel.ChangeSet{
		Kind: filemodel.ChangeUpdate, FileID: file.ID, CircleID: file.CircleID,
		ExpectedVersion: command.ExpectedVersion, ParentFolderID: command.ParentFolderID,
		Name: command.Name, OccurredAt: facade.now().UTC(),
	}, policy.QuotaBytes)
}

func (facade *CommandFacade) Delete(ctx context.Context, command DeleteCommand) (CommandResult, error) {
	current, actorID, err := trustedFileCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	file, found, err := facade.store.Load(ctx, strings.TrimSpace(command.FileID))
	if err != nil {
		return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || file.CircleID != strings.TrimSpace(command.CircleID) {
		return CommandResult{}, generated.AppErrorFromFileNotFound("CircleFile not found in Circle")
	}
	policy, err := facade.requireSpaceAccess(ctx, file.CircleID, file.GroupID, actorID, file.UploaderPersonaID != actorID)
	if err != nil {
		return CommandResult{}, err
	}
	change := filemodel.ChangeSet{
		Kind: filemodel.ChangeDelete, FileID: file.ID, CircleID: file.CircleID,
		ExpectedVersion: file.Version, OccurredAt: facade.now().UTC(),
	}
	if file.Status == filemodel.CircleFileStatusDeleted {
		return facade.recordNoop(ctx, current, actorID, file, change)
	}
	return facade.commit(ctx, current, actorID, change, policy.QuotaBytes)
}

// recordNoop 持久化"目标状态已满足"回执；首个 Idempotency-Key 也能重放原始结果。
func (facade *CommandFacade) recordNoop(ctx context.Context, current operation.Context, actorID string, file filemodel.CircleFile, change filemodel.ChangeSet) (CommandResult, error) {
	digest, err := fileCommandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	receipt, err := facade.store.RecordNoopReceipt(ctx, fileports.NoopReceipt{
		FileID: file.ID, Version: file.Version, Status: file.Status,
		ReceiptKey:    fileReceiptKey(actorID, current.IdempotencyKey),
		CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(fileReceiptRetention),
	})
	if err != nil {
		return CommandResult{}, mapFileCommitError(err)
	}
	return CommandResult{
		FileID: receipt.FileID, Version: receipt.Version,
		Status: string(receipt.Status), IdempotentReplay: true,
	}, nil
}

func (facade *CommandFacade) requireSpaceAccess(ctx context.Context, circleID, groupID, personaID string, elevated bool) (fileports.CircleStoragePolicySlice, error) {
	policy, found, err := facade.policies.ReadCircleStoragePolicy(ctx, strings.TrimSpace(circleID))
	if err != nil {
		return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || policy.State != "active" || policy.QuotaBytes <= 0 {
		return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromCircleNotFound("active Circle storage policy is required")
	}
	membership, found, err := facade.policies.ReadCircleMembership(ctx, policy.CircleID, personaID)
	if err != nil {
		return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || membership.State != "active" {
		return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromNotMember("active CircleMembership is required")
	}
	if strings.TrimSpace(groupID) != "" {
		groupMembership, groupFound, groupErr := facade.policies.ReadGroupMembership(ctx, strings.TrimSpace(groupID), personaID)
		if groupErr != nil {
			return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromFileStorageWriteFailed(groupErr.Error())
		}
		if !groupFound || groupMembership.State != "active" {
			return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromNotMember("active CircleGroupMembership is required")
		}
		if elevated && groupMembership.Role != "owner" && groupMembership.Role != "manager" {
			return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromPermissionDenied("CircleGroup owner or manager is required")
		}
	} else if elevated && membership.Role != "owner" && membership.Role != "admin" {
		return fileports.CircleStoragePolicySlice{}, generated.AppErrorFromPermissionDenied("Circle owner or admin is required")
	}
	return policy, nil
}

func (facade *CommandFacade) validateParent(ctx context.Context, circleID, groupID, fileID string, parentID *string) error {
	if parentID == nil || strings.TrimSpace(*parentID) == "" {
		return nil
	}
	parent, found, err := facade.policies.ReadParentFolder(ctx, strings.TrimSpace(circleID), strings.TrimSpace(*parentID))
	if err != nil {
		return generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || parent.Status != filemodel.CircleFileStatusActive || parent.FileType != filemodel.CircleFileTypeFolder ||
		parent.GroupID != strings.TrimSpace(groupID) || parent.ID == fileID {
		return generated.AppErrorFromFileParentInvalid("parent must be an active folder in the same Circle space")
	}
	contains, err := facade.policies.ParentChainContains(ctx, strings.TrimSpace(circleID), parent.ID, fileID)
	if err != nil {
		return generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if contains {
		return generated.AppErrorFromFileParentInvalid("parent chain would form a cycle")
	}
	return nil
}

func (facade *CommandFacade) commit(ctx context.Context, current operation.Context, actorID string, change filemodel.ChangeSet, quota int64) (CommandResult, error) {
	digest, err := fileCommandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := facade.store.Commit(ctx, fileports.CommitRequest{
			Change: change, ReceiptKey: fileReceiptKey(actorID, current.IdempotencyKey), CommandDigest: digest,
			ReceiptExpiresAt: facade.now().UTC().Add(fileReceiptRetention), StorageQuota: quota,
		})
		if commitErr == nil {
			return CommandResult{FileID: receipt.FileID, Version: receipt.Version, Status: string(receipt.Status), IdempotentReplay: receipt.Replayed}, nil
		}
		if change.Kind != filemodel.ChangeDelete ||
			!errors.Is(commitErr, filemodel.ErrVersionConflict) ||
			attempt == 2 {
			return CommandResult{}, mapFileCommitError(commitErr)
		}
		latest, found, loadErr := facade.store.Load(ctx, change.FileID)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromFileStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CommandResult{}, mapFileCommitError(filemodel.ErrNotFound)
		}
		if latest.Status == filemodel.CircleFileStatusDeleted {
			return facade.recordNoop(ctx, current, actorID, latest, change)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable CircleFile commit retry")
}

func trustedFileCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func fileCommandDigest(actorID string, change filemodel.ChangeSet) (string, error) {
	copy := change
	copy.OccurredAt = time.Time{}
	if copy.Kind == filemodel.ChangeDelete {
		copy.ExpectedVersion = 0
	}
	payload, err := json.Marshal(struct {
		ActorID string              `json:"actorId"`
		Change  filemodel.ChangeSet `json:"change"`
	}{ActorID: actorID, Change: copy})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func fileReceiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return hex.EncodeToString(sum[:])
}

func stableFileID(circleID, actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(circleID) + "\x00" + strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "cf_" + hex.EncodeToString(sum[:16])
}

func mapFileCommitError(err error) error {
	switch {
	case errors.Is(err, filemodel.ErrNotFound), errors.Is(err, filemodel.ErrDeleted):
		return generated.AppErrorFromFileNotFound(err.Error())
	case errors.Is(err, filemodel.ErrParentInvalid):
		return generated.AppErrorFromFileParentInvalid(err.Error())
	case errors.Is(err, filemodel.ErrAssetInvalid):
		return generated.AppErrorFromFileAssetInvalid(err.Error())
	case errors.Is(err, filemodel.ErrQuotaExceeded):
		return generated.AppErrorFromStorageQuotaExceeded(err.Error())
	case errors.Is(err, filemodel.ErrVersionConflict):
		return generated.AppErrorFromFileVersionConflict(err.Error())
	case errors.Is(err, filemodel.ErrIdempotencyConflict):
		return generated.AppErrorFromFileIdempotencyConflict(err.Error())
	case errors.Is(err, filemodel.ErrInvalidChange):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
}

type FileSlice struct {
	FileID            string                     `json:"fileId"`
	Version           int64                      `json:"version"`
	CircleID          string                     `json:"circleId"`
	GroupID           string                     `json:"groupId,omitempty"`
	ParentFolderID    string                     `json:"parentFolderId,omitempty"`
	Name              string                     `json:"name"`
	FileType          filemodel.CircleFileType   `json:"fileType"`
	AssetID           string                     `json:"assetId,omitempty"`
	MimeType          string                     `json:"mimeType,omitempty"`
	SizeBytes         int64                      `json:"sizeBytes"`
	UploaderPersonaID string                     `json:"uploaderPersonaId"`
	Status            filemodel.CircleFileStatus `json:"status"`
	CreatedAt         time.Time                  `json:"createdAt"`
	UpdatedAt         time.Time                  `json:"updatedAt"`
}

type PageResult struct {
	Items  []FileSlice `json:"items"`
	Cursor string      `json:"cursor,omitempty"`
}

type QueryFacade struct {
	readers  fileports.Reader
	policies fileports.PolicyReader
}

func NewQueryFacade(readers fileports.Reader, policies fileports.PolicyReader) *QueryFacade {
	if readers == nil || policies == nil {
		panic("CircleFile QueryFacade requires named Readers")
	}
	return &QueryFacade{readers: readers, policies: policies}
}

func (facade *QueryFacade) Get(ctx context.Context, circleID, fileID string) (FileSlice, error) {
	if _, err := facade.requireReadAccess(ctx, circleID, ""); err != nil {
		return FileSlice{}, err
	}
	file, found, err := facade.readers.ReadFile(ctx, strings.TrimSpace(circleID), strings.TrimSpace(fileID))
	if err != nil {
		return FileSlice{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found {
		return FileSlice{}, generated.AppErrorFromFileNotFound("CircleFile not found")
	}
	if _, err := facade.requireReadAccess(ctx, file.CircleID, file.GroupID); err != nil {
		return FileSlice{}, err
	}
	return newFileSlice(file), nil
}

func (facade *QueryFacade) List(ctx context.Context, query fileports.ListQuery) (PageResult, error) {
	if _, err := facade.requireReadAccess(ctx, query.CircleID, query.GroupID); err != nil {
		return PageResult{}, err
	}
	page, err := facade.readers.ListFiles(ctx, query)
	if err != nil {
		return PageResult{}, generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	result := PageResult{Items: make([]FileSlice, 0, len(page.Items)), Cursor: page.Cursor}
	for _, file := range page.Items {
		result.Items = append(result.Items, newFileSlice(file))
	}
	return result, nil
}

func (facade *QueryFacade) requireReadAccess(ctx context.Context, circleID, groupID string) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", generated.AppErrorFromInvalidArgument("trusted persona is required")
	}
	actorID := strings.TrimSpace(current.Actor.PersonaID)
	membership, found, err := facade.policies.ReadCircleMembership(ctx, strings.TrimSpace(circleID), actorID)
	if err != nil {
		return "", generated.AppErrorFromFileStorageWriteFailed(err.Error())
	}
	if !found || membership.State != "active" {
		return "", generated.AppErrorFromNotMember("active CircleMembership is required")
	}
	if strings.TrimSpace(groupID) != "" {
		groupMembership, groupFound, groupErr := facade.policies.ReadGroupMembership(ctx, strings.TrimSpace(groupID), actorID)
		if groupErr != nil {
			return "", generated.AppErrorFromFileStorageWriteFailed(groupErr.Error())
		}
		if !groupFound || groupMembership.State != "active" {
			return "", generated.AppErrorFromNotMember("active CircleGroupMembership is required")
		}
	}
	return actorID, nil
}

func newFileSlice(file filemodel.CircleFile) FileSlice {
	return FileSlice{
		FileID: file.ID, Version: file.Version, CircleID: file.CircleID, GroupID: file.GroupID,
		ParentFolderID: file.ParentFolderID, Name: file.Name, FileType: file.FileType,
		AssetID: file.AssetID, MimeType: file.MimeType, SizeBytes: file.SizeBytes,
		UploaderPersonaID: file.UploaderPersonaID, Status: file.Status,
		CreatedAt: file.CreatedAt, UpdatedAt: file.UpdatedAt,
	}
}
