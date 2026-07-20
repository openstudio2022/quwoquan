package model

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

var sha256DigestPattern = regexp.MustCompile(`^(sha256:)?[0-9a-f]{64}$`)

var (
	ErrInvalidUploadSession           = errors.New("invalid media upload session")
	ErrInvalidUploadSessionTransition = errors.New("invalid media upload session transition")
	ErrUploadSessionExpired           = errors.New("media upload session expired")
	ErrUploadSessionOwnerForbidden    = errors.New("media upload session owner forbidden")
	ErrUploadDigestMismatch           = errors.New("media upload digest mismatch")
)

type UploadSessionStatus string

const (
	UploadSessionPending   UploadSessionStatus = "pending"
	UploadSessionCompleted UploadSessionStatus = "completed"
	UploadSessionAborted   UploadSessionStatus = "aborted"
)

// UploadSessionSnapshot is the persistence boundary for MediaUploadSession.
// It deliberately contains no transport-only fields.
type UploadSessionSnapshot struct {
	ID             string
	Version        int64
	OwnerID        string
	ObjectKey      string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
	AssetID        string
	Status         UploadSessionStatus
	CreatedAt      time.Time
	UpdatedAt      time.Time
	ExpiresAt      time.Time
	CompletedAt    *time.Time
	AbortedAt      *time.Time
}

type CreateUploadSessionParams struct {
	ID             string
	OwnerID        string
	ObjectKey      string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
	ExpiresAt      time.Time
	Now            time.Time
}

// MediaUploadSession owns the short-lived upload protocol and never embeds a
// MediaAsset. A completion command atomically creates a separate asset through
// the application/store transaction.
type MediaUploadSession struct {
	id             string
	version        int64
	ownerID        string
	objectKey      string
	mediaType      string
	contentType    string
	fileSize       int64
	expectedSHA256 string
	assetID        string
	status         UploadSessionStatus
	createdAt      time.Time
	updatedAt      time.Time
	expiresAt      time.Time
	completedAt    *time.Time
	abortedAt      *time.Time
}

func CreateUploadSession(params CreateUploadSessionParams) (*MediaUploadSession, error) {
	now := params.Now.UTC()
	session := &MediaUploadSession{
		id:             strings.TrimSpace(params.ID),
		version:        1,
		ownerID:        strings.TrimSpace(params.OwnerID),
		objectKey:      strings.TrimSpace(params.ObjectKey),
		mediaType:      strings.TrimSpace(params.MediaType),
		contentType:    strings.TrimSpace(params.ContentType),
		fileSize:       params.FileSize,
		expectedSHA256: normalizeDigest(params.ExpectedSHA256),
		status:         UploadSessionPending,
		createdAt:      now,
		updatedAt:      now,
		expiresAt:      params.ExpiresAt.UTC(),
	}
	if err := session.validate(); err != nil {
		return nil, err
	}
	if !session.expiresAt.After(now) {
		return nil, fmt.Errorf("%w: expiration must be after creation", ErrInvalidUploadSession)
	}
	return session, nil
}

func RestoreUploadSession(snapshot UploadSessionSnapshot) (*MediaUploadSession, error) {
	session := &MediaUploadSession{
		id:             strings.TrimSpace(snapshot.ID),
		version:        snapshot.Version,
		ownerID:        strings.TrimSpace(snapshot.OwnerID),
		objectKey:      strings.TrimSpace(snapshot.ObjectKey),
		mediaType:      strings.TrimSpace(snapshot.MediaType),
		contentType:    strings.TrimSpace(snapshot.ContentType),
		fileSize:       snapshot.FileSize,
		expectedSHA256: normalizeDigest(snapshot.ExpectedSHA256),
		assetID:        strings.TrimSpace(snapshot.AssetID),
		status:         snapshot.Status,
		createdAt:      snapshot.CreatedAt.UTC(),
		updatedAt:      snapshot.UpdatedAt.UTC(),
		expiresAt:      snapshot.ExpiresAt.UTC(),
		completedAt:    cloneTime(snapshot.CompletedAt),
		abortedAt:      cloneTime(snapshot.AbortedAt),
	}
	if err := session.validate(); err != nil {
		return nil, err
	}
	return session, nil
}

func (s *MediaUploadSession) Complete(
	ownerID string,
	actualSHA256 string,
	assetID string,
	now time.Time,
) error {
	if s == nil {
		return fmt.Errorf("%w: session is required", ErrInvalidUploadSession)
	}
	if strings.TrimSpace(ownerID) != s.ownerID {
		return fmt.Errorf("%w: completion owner does not match", ErrUploadSessionOwnerForbidden)
	}
	if s.status != UploadSessionPending {
		return fmt.Errorf("%w: only pending sessions can complete", ErrInvalidUploadSessionTransition)
	}
	now = now.UTC()
	if now.IsZero() || !now.Before(s.expiresAt) {
		return fmt.Errorf("%w: expiresAt=%s", ErrUploadSessionExpired, s.expiresAt.Format(time.RFC3339Nano))
	}
	if normalizeDigest(actualSHA256) != s.expectedSHA256 {
		return fmt.Errorf("%w: upload callback digest differs from expected digest", ErrUploadDigestMismatch)
	}
	assetID = strings.TrimSpace(assetID)
	if assetID == "" {
		return fmt.Errorf("%w: completed asset id is required", ErrInvalidUploadSession)
	}
	if err := s.advance(now); err != nil {
		return err
	}
	completedAt := s.updatedAt
	s.status = UploadSessionCompleted
	s.assetID = assetID
	s.completedAt = &completedAt
	return nil
}

func (s *MediaUploadSession) Abort(ownerID string, now time.Time) error {
	if s == nil {
		return fmt.Errorf("%w: session is required", ErrInvalidUploadSession)
	}
	if strings.TrimSpace(ownerID) != s.ownerID {
		return fmt.Errorf("%w: abort owner does not match", ErrUploadSessionOwnerForbidden)
	}
	if s.status != UploadSessionPending {
		return fmt.Errorf("%w: only pending sessions can abort", ErrInvalidUploadSessionTransition)
	}
	if err := s.advance(now); err != nil {
		return err
	}
	abortedAt := s.updatedAt
	s.status = UploadSessionAborted
	s.abortedAt = &abortedAt
	return nil
}

func (s *MediaUploadSession) ID() string {
	if s == nil {
		return ""
	}
	return s.id
}

func (s *MediaUploadSession) Version() int64 {
	if s == nil {
		return 0
	}
	return s.version
}

func (s *MediaUploadSession) OwnerID() string {
	if s == nil {
		return ""
	}
	return s.ownerID
}

func (s *MediaUploadSession) ObjectKey() string {
	if s == nil {
		return ""
	}
	return s.objectKey
}

func (s *MediaUploadSession) ExpectedSHA256() string {
	if s == nil {
		return ""
	}
	return s.expectedSHA256
}

func (s *MediaUploadSession) AssetID() string {
	if s == nil {
		return ""
	}
	return s.assetID
}

func (s *MediaUploadSession) MediaType() string {
	if s == nil {
		return ""
	}
	return s.mediaType
}

func (s *MediaUploadSession) ContentType() string {
	if s == nil {
		return ""
	}
	return s.contentType
}

func (s *MediaUploadSession) FileSize() int64 {
	if s == nil {
		return 0
	}
	return s.fileSize
}

func (s *MediaUploadSession) Status() UploadSessionStatus {
	if s == nil {
		return ""
	}
	return s.status
}

func (s *MediaUploadSession) ExpiresAt() time.Time {
	if s == nil {
		return time.Time{}
	}
	return s.expiresAt
}

func (s *MediaUploadSession) Snapshot() UploadSessionSnapshot {
	if s == nil {
		return UploadSessionSnapshot{}
	}
	return UploadSessionSnapshot{
		ID:             s.id,
		Version:        s.version,
		OwnerID:        s.ownerID,
		ObjectKey:      s.objectKey,
		MediaType:      s.mediaType,
		ContentType:    s.contentType,
		FileSize:       s.fileSize,
		ExpectedSHA256: s.expectedSHA256,
		AssetID:        s.assetID,
		Status:         s.status,
		CreatedAt:      s.createdAt,
		UpdatedAt:      s.updatedAt,
		ExpiresAt:      s.expiresAt,
		CompletedAt:    cloneTime(s.completedAt),
		AbortedAt:      cloneTime(s.abortedAt),
	}
}

func (s *MediaUploadSession) validate() error {
	if s == nil ||
		s.id == "" ||
		s.version < 1 ||
		s.ownerID == "" ||
		s.objectKey == "" ||
		s.mediaType == "" ||
		s.contentType == "" ||
		s.fileSize <= 0 ||
		!sha256DigestPattern.MatchString(s.expectedSHA256) ||
		!validUploadSessionStatus(s.status) ||
		s.createdAt.IsZero() ||
		s.updatedAt.IsZero() ||
		s.updatedAt.Before(s.createdAt) ||
		s.expiresAt.IsZero() ||
		!s.expiresAt.After(s.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidUploadSession)
	}
	switch s.status {
	case UploadSessionPending:
		if s.assetID != "" || s.completedAt != nil || s.abortedAt != nil {
			return fmt.Errorf("%w: pending session carries terminal time", ErrInvalidUploadSession)
		}
	case UploadSessionCompleted:
		if s.assetID == "" || s.completedAt == nil || s.abortedAt != nil {
			return fmt.Errorf("%w: completed session state is inconsistent", ErrInvalidUploadSession)
		}
	case UploadSessionAborted:
		if s.assetID != "" || s.abortedAt == nil || s.completedAt != nil {
			return fmt.Errorf("%w: aborted session state is inconsistent", ErrInvalidUploadSession)
		}
	}
	return nil
}

func (s *MediaUploadSession) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(s.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidUploadSession)
	}
	s.version++
	s.updatedAt = now
	return nil
}

func validUploadSessionStatus(value UploadSessionStatus) bool {
	switch value {
	case UploadSessionPending, UploadSessionCompleted, UploadSessionAborted:
		return true
	default:
		return false
	}
}
