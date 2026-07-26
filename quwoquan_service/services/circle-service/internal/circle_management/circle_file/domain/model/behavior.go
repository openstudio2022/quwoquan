package circlefile

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidChange       = errors.New("invalid CircleFile change")
	ErrNotFound            = errors.New("CircleFile not found")
	ErrDeleted             = errors.New("CircleFile is deleted")
	ErrVersionConflict     = errors.New("CircleFile version conflict")
	ErrIdempotencyConflict = errors.New("CircleFile idempotency conflict")
	ErrParentInvalid       = errors.New("CircleFile parent is invalid")
	ErrAssetInvalid        = errors.New("CircleFile MediaAsset is invalid")
	ErrQuotaExceeded       = errors.New("CircleFile quota exceeded")
)

type ChangeKind string

const (
	ChangeCreate ChangeKind = "create"
	ChangeUpdate ChangeKind = "update"
	ChangeDelete ChangeKind = "delete"
)

type ChangeSet struct {
	Kind              ChangeKind
	FileID            string
	ExpectedVersion   int64
	CircleID          string
	GroupID           string
	ParentFolderID    *string
	Name              *string
	FileType          CircleFileType
	AssetID           string
	MimeType          string
	SizeBytes         int64
	UploaderPersonaID string
	OccurredAt        time.Time
}

func Apply(current *CircleFile, change ChangeSet) (CircleFile, error) {
	switch change.Kind {
	case ChangeCreate:
		if current != nil || change.ExpectedVersion != 0 {
			return CircleFile{}, ErrVersionConflict
		}
		if err := validateCreate(change); err != nil {
			return CircleFile{}, err
		}
		return CircleFile{
			ID: strings.TrimSpace(change.FileID), Version: 1,
			CircleID: strings.TrimSpace(change.CircleID), GroupID: strings.TrimSpace(change.GroupID),
			ParentFolderID: optionalValue(change.ParentFolderID), Name: strings.TrimSpace(*change.Name),
			FileType: change.FileType, AssetID: strings.TrimSpace(change.AssetID),
			MimeType: strings.TrimSpace(change.MimeType), SizeBytes: change.SizeBytes,
			UploaderPersonaID: strings.TrimSpace(change.UploaderPersonaID), Status: CircleFileStatusActive,
			CreatedAt: change.OccurredAt.UTC(), UpdatedAt: change.OccurredAt.UTC(),
		}, nil
	case ChangeUpdate:
		if err := validateCurrent(current, change); err != nil {
			return CircleFile{}, err
		}
		if change.Name == nil && change.ParentFolderID == nil {
			return CircleFile{}, ErrInvalidChange
		}
		next := *current
		if change.Name != nil {
			name := strings.TrimSpace(*change.Name)
			if name == "" || len([]rune(name)) > 255 {
				return CircleFile{}, ErrInvalidChange
			}
			next.Name = name
		}
		if change.ParentFolderID != nil {
			next.ParentFolderID = strings.TrimSpace(*change.ParentFolderID)
		}
		next.Version++
		next.UpdatedAt = change.OccurredAt.UTC()
		return next, nil
	case ChangeDelete:
		if err := validateCurrent(current, change); err != nil {
			return CircleFile{}, err
		}
		next := *current
		next.Version++
		next.Status = CircleFileStatusDeleted
		next.UpdatedAt = change.OccurredAt.UTC()
		return next, nil
	default:
		return CircleFile{}, ErrInvalidChange
	}
}

func validateCreate(change ChangeSet) error {
	if strings.TrimSpace(change.FileID) == "" || strings.TrimSpace(change.CircleID) == "" ||
		strings.TrimSpace(change.UploaderPersonaID) == "" || change.Name == nil || change.OccurredAt.IsZero() {
		return ErrInvalidChange
	}
	name := strings.TrimSpace(*change.Name)
	if name == "" || len([]rune(name)) > 255 {
		return ErrInvalidChange
	}
	switch change.FileType {
	case CircleFileTypeFile:
		if strings.TrimSpace(change.AssetID) == "" || strings.TrimSpace(change.MimeType) == "" || change.SizeBytes <= 0 {
			return ErrAssetInvalid
		}
	case CircleFileTypeFolder:
		if strings.TrimSpace(change.AssetID) != "" || strings.TrimSpace(change.MimeType) != "" || change.SizeBytes != 0 {
			return ErrAssetInvalid
		}
	default:
		return ErrInvalidChange
	}
	return nil
}

func validateCurrent(current *CircleFile, change ChangeSet) error {
	if current == nil {
		return ErrNotFound
	}
	if current.Status == CircleFileStatusDeleted {
		return ErrDeleted
	}
	if change.ExpectedVersion <= 0 || current.Version != change.ExpectedVersion {
		return ErrVersionConflict
	}
	if strings.TrimSpace(change.FileID) != current.ID ||
		(change.CircleID != "" && strings.TrimSpace(change.CircleID) != current.CircleID) {
		return ErrInvalidChange
	}
	return nil
}

func optionalValue(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}
