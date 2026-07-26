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
	ErrInvalidSession           = errors.New("invalid media upload session")
	ErrInvalidSessionTransition = errors.New("invalid media upload session transition")
	ErrSessionExpired           = errors.New("media upload session expired")
	ErrSessionOwnerForbidden    = errors.New("media upload session owner forbidden")
	ErrDigestMismatch           = errors.New("media upload digest mismatch")
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusCompleted Status = "completed"
	StatusAborted   Status = "aborted"
)

// Snapshot is the durable boundary of the MediaUploadSession aggregate.
type Snapshot struct {
	ID             string
	Version        int64
	OwnerID        string
	ObjectKey      string
	MediaType      string
	ContentType    string
	FileSize       int64
	ExpectedSHA256 string
	AssetID        string
	Status         Status
	CreatedAt      time.Time
	UpdatedAt      time.Time
	ExpiresAt      time.Time
	CompletedAt    *time.Time
	AbortedAt      *time.Time
}

type CreateParams struct {
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

type Session struct {
	snapshot Snapshot
}

func Create(params CreateParams) (*Session, error) {
	now := params.Now.UTC()
	session := &Session{snapshot: Snapshot{
		ID:             strings.TrimSpace(params.ID),
		Version:        1,
		OwnerID:        strings.TrimSpace(params.OwnerID),
		ObjectKey:      strings.TrimSpace(params.ObjectKey),
		MediaType:      strings.TrimSpace(params.MediaType),
		ContentType:    strings.TrimSpace(params.ContentType),
		FileSize:       params.FileSize,
		ExpectedSHA256: normalizeDigest(params.ExpectedSHA256),
		Status:         StatusPending,
		CreatedAt:      now,
		UpdatedAt:      now,
		ExpiresAt:      params.ExpiresAt.UTC(),
	}}
	if err := session.validate(); err != nil {
		return nil, err
	}
	if !session.snapshot.ExpiresAt.After(now) {
		return nil, fmt.Errorf("%w: expiration must be after creation", ErrInvalidSession)
	}
	return session, nil
}

func Restore(snapshot Snapshot) (*Session, error) {
	session := &Session{snapshot: Snapshot{
		ID:             strings.TrimSpace(snapshot.ID),
		Version:        snapshot.Version,
		OwnerID:        strings.TrimSpace(snapshot.OwnerID),
		ObjectKey:      strings.TrimSpace(snapshot.ObjectKey),
		MediaType:      strings.TrimSpace(snapshot.MediaType),
		ContentType:    strings.TrimSpace(snapshot.ContentType),
		FileSize:       snapshot.FileSize,
		ExpectedSHA256: normalizeDigest(snapshot.ExpectedSHA256),
		AssetID:        strings.TrimSpace(snapshot.AssetID),
		Status:         snapshot.Status,
		CreatedAt:      snapshot.CreatedAt.UTC(),
		UpdatedAt:      snapshot.UpdatedAt.UTC(),
		ExpiresAt:      snapshot.ExpiresAt.UTC(),
		CompletedAt:    cloneTime(snapshot.CompletedAt),
		AbortedAt:      cloneTime(snapshot.AbortedAt),
	}}
	if err := session.validate(); err != nil {
		return nil, err
	}
	return session, nil
}

func (s *Session) Complete(ownerID, actualSHA256, assetID string, now time.Time) error {
	if s == nil {
		return fmt.Errorf("%w: session is required", ErrInvalidSession)
	}
	if strings.TrimSpace(ownerID) != s.snapshot.OwnerID {
		return fmt.Errorf("%w: completion owner does not match", ErrSessionOwnerForbidden)
	}
	if s.snapshot.Status != StatusPending {
		return fmt.Errorf("%w: only pending sessions can complete", ErrInvalidSessionTransition)
	}
	now = now.UTC()
	if now.IsZero() || !now.Before(s.snapshot.ExpiresAt) {
		return fmt.Errorf("%w: expiresAt=%s", ErrSessionExpired, s.snapshot.ExpiresAt.Format(time.RFC3339Nano))
	}
	if normalizeDigest(actualSHA256) != s.snapshot.ExpectedSHA256 {
		return fmt.Errorf("%w: upload callback digest differs from expected digest", ErrDigestMismatch)
	}
	assetID = strings.TrimSpace(assetID)
	if assetID == "" {
		return fmt.Errorf("%w: completed asset id is required", ErrInvalidSession)
	}
	if err := s.advance(now); err != nil {
		return err
	}
	s.snapshot.Status = StatusCompleted
	s.snapshot.AssetID = assetID
	completedAt := s.snapshot.UpdatedAt
	s.snapshot.CompletedAt = &completedAt
	return nil
}

func (s *Session) Abort(ownerID string, now time.Time) error {
	if s == nil {
		return fmt.Errorf("%w: session is required", ErrInvalidSession)
	}
	if strings.TrimSpace(ownerID) != s.snapshot.OwnerID {
		return fmt.Errorf("%w: abort owner does not match", ErrSessionOwnerForbidden)
	}
	if s.snapshot.Status != StatusPending {
		return fmt.Errorf("%w: only pending sessions can abort", ErrInvalidSessionTransition)
	}
	if err := s.advance(now); err != nil {
		return err
	}
	s.snapshot.Status = StatusAborted
	abortedAt := s.snapshot.UpdatedAt
	s.snapshot.AbortedAt = &abortedAt
	return nil
}

func (s *Session) Snapshot() Snapshot {
	if s == nil {
		return Snapshot{}
	}
	snapshot := s.snapshot
	snapshot.CompletedAt = cloneTime(snapshot.CompletedAt)
	snapshot.AbortedAt = cloneTime(snapshot.AbortedAt)
	return snapshot
}

func (s *Session) ID() string             { return s.Snapshot().ID }
func (s *Session) Version() int64         { return s.Snapshot().Version }
func (s *Session) OwnerID() string        { return s.Snapshot().OwnerID }
func (s *Session) ObjectKey() string      { return s.Snapshot().ObjectKey }
func (s *Session) MediaType() string      { return s.Snapshot().MediaType }
func (s *Session) ContentType() string    { return s.Snapshot().ContentType }
func (s *Session) FileSize() int64        { return s.Snapshot().FileSize }
func (s *Session) ExpectedSHA256() string { return s.Snapshot().ExpectedSHA256 }
func (s *Session) AssetID() string        { return s.Snapshot().AssetID }
func (s *Session) Status() Status         { return s.Snapshot().Status }
func (s *Session) ExpiresAt() time.Time   { return s.Snapshot().ExpiresAt }

func (s *Session) validate() error {
	if s == nil ||
		s.snapshot.ID == "" ||
		s.snapshot.Version < 1 ||
		s.snapshot.OwnerID == "" ||
		s.snapshot.ObjectKey == "" ||
		s.snapshot.MediaType == "" ||
		s.snapshot.ContentType == "" ||
		s.snapshot.FileSize <= 0 ||
		!sha256DigestPattern.MatchString(s.snapshot.ExpectedSHA256) ||
		!validStatus(s.snapshot.Status) ||
		s.snapshot.CreatedAt.IsZero() ||
		s.snapshot.UpdatedAt.IsZero() ||
		s.snapshot.UpdatedAt.Before(s.snapshot.CreatedAt) ||
		s.snapshot.ExpiresAt.IsZero() ||
		!s.snapshot.ExpiresAt.After(s.snapshot.CreatedAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidSession)
	}
	switch s.snapshot.Status {
	case StatusPending:
		if s.snapshot.AssetID != "" || s.snapshot.CompletedAt != nil || s.snapshot.AbortedAt != nil {
			return fmt.Errorf("%w: pending session carries terminal state", ErrInvalidSession)
		}
	case StatusCompleted:
		if s.snapshot.AssetID == "" || s.snapshot.CompletedAt == nil || s.snapshot.AbortedAt != nil {
			return fmt.Errorf("%w: completed session state is inconsistent", ErrInvalidSession)
		}
	case StatusAborted:
		if s.snapshot.AssetID != "" || s.snapshot.AbortedAt == nil || s.snapshot.CompletedAt != nil {
			return fmt.Errorf("%w: aborted session state is inconsistent", ErrInvalidSession)
		}
	}
	return nil
}

func (s *Session) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(s.snapshot.UpdatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidSession)
	}
	s.snapshot.Version++
	s.snapshot.UpdatedAt = now
	return nil
}

func validStatus(status Status) bool {
	return status == StatusPending || status == StatusCompleted || status == StatusAborted
}

func normalizeDigest(value string) string {
	return strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
