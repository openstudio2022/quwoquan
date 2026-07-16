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
	ErrInvalidMediaAsset              = errors.New("invalid media asset")
	ErrInvalidMediaAssetTransition    = errors.New("invalid media asset transition")
	ErrMediaAssetOwnerForbidden       = errors.New("media asset owner forbidden")
)

type UploadSessionStatus string

const (
	UploadSessionPending   UploadSessionStatus = "pending"
	UploadSessionCompleted UploadSessionStatus = "completed"
	UploadSessionAborted   UploadSessionStatus = "aborted"
)

type AccessPolicy string

const (
	AccessPolicyOwnerOnly      AccessPolicy = "owner_only"
	AccessPolicyReferencedPost AccessPolicy = "referenced_post"
	AccessPolicyPublic         AccessPolicy = "public"
)

type ProcessingStatus string

const (
	ProcessingStatusProcessing ProcessingStatus = "processing"
	ProcessingStatusReady      ProcessingStatus = "ready"
	ProcessingStatusRejected   ProcessingStatus = "rejected"
	ProcessingStatusDeleted    ProcessingStatus = "deleted"
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

func (s *MediaUploadSession) Complete(ownerID string, actualSHA256 string, now time.Time) error {
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
	if err := s.advance(now); err != nil {
		return err
	}
	completedAt := s.updatedAt
	s.status = UploadSessionCompleted
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
		if s.completedAt != nil || s.abortedAt != nil {
			return fmt.Errorf("%w: pending session carries terminal time", ErrInvalidUploadSession)
		}
	case UploadSessionCompleted:
		if s.completedAt == nil || s.abortedAt != nil {
			return fmt.Errorf("%w: completed session state is inconsistent", ErrInvalidUploadSession)
		}
	case UploadSessionAborted:
		if s.abortedAt == nil || s.completedAt != nil {
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

// MediaAssetSnapshot is the persistence boundary for MediaAsset.
type MediaAssetSnapshot struct {
	ID                      string
	Version                 int64
	OwnerID                 string
	SourceSessionID         string
	ObjectKey               string
	SHA256                  string
	MediaType               string
	ContentType             string
	FileSize                int64
	AccessPolicy            AccessPolicy
	ProcessingStatus        ProcessingStatus
	ProcessingFailureReason string
	CoverStrategy           string
	ManualCoverAssetID      string
	CoverFrameTimeMs        int64
	CreatedAt               time.Time
	UpdatedAt               time.Time
	ProcessedAt             *time.Time
}

type CreateMediaAssetParams struct {
	ID                 string
	OwnerID            string
	SourceSessionID    string
	ObjectKey          string
	SHA256             string
	MediaType          string
	ContentType        string
	FileSize           int64
	AccessPolicy       AccessPolicy
	ProcessingRequired bool
	Now                time.Time
}

// MediaAsset is a durable, independently authorized media object. It never
// derives its owner or processing state from PostService process-local maps.
type MediaAsset struct {
	id                      string
	version                 int64
	ownerID                 string
	sourceSessionID         string
	objectKey               string
	sha256                  string
	mediaType               string
	contentType             string
	fileSize                int64
	accessPolicy            AccessPolicy
	processingStatus        ProcessingStatus
	processingFailureReason string
	coverStrategy           string
	manualCoverAssetID      string
	coverFrameTimeMs        int64
	createdAt               time.Time
	updatedAt               time.Time
	processedAt             *time.Time
}

func CreateMediaAsset(params CreateMediaAssetParams) (*MediaAsset, error) {
	now := params.Now.UTC()
	asset := &MediaAsset{
		id:               strings.TrimSpace(params.ID),
		version:          1,
		ownerID:          strings.TrimSpace(params.OwnerID),
		sourceSessionID:  strings.TrimSpace(params.SourceSessionID),
		objectKey:        strings.TrimSpace(params.ObjectKey),
		sha256:           normalizeDigest(params.SHA256),
		mediaType:        strings.TrimSpace(params.MediaType),
		contentType:      strings.TrimSpace(params.ContentType),
		fileSize:         params.FileSize,
		accessPolicy:     params.AccessPolicy,
		processingStatus: ProcessingStatusReady,
		coverStrategy:    "first_frame",
		createdAt:        now,
		updatedAt:        now,
	}
	if params.ProcessingRequired {
		asset.processingStatus = ProcessingStatusProcessing
	} else {
		processedAt := now
		asset.processedAt = &processedAt
	}
	if err := asset.validate(); err != nil {
		return nil, err
	}
	return asset, nil
}

func RestoreMediaAsset(snapshot MediaAssetSnapshot) (*MediaAsset, error) {
	asset := &MediaAsset{
		id:                      strings.TrimSpace(snapshot.ID),
		version:                 snapshot.Version,
		ownerID:                 strings.TrimSpace(snapshot.OwnerID),
		sourceSessionID:         strings.TrimSpace(snapshot.SourceSessionID),
		objectKey:               strings.TrimSpace(snapshot.ObjectKey),
		sha256:                  normalizeDigest(snapshot.SHA256),
		mediaType:               strings.TrimSpace(snapshot.MediaType),
		contentType:             strings.TrimSpace(snapshot.ContentType),
		fileSize:                snapshot.FileSize,
		accessPolicy:            snapshot.AccessPolicy,
		processingStatus:        snapshot.ProcessingStatus,
		processingFailureReason: strings.TrimSpace(snapshot.ProcessingFailureReason),
		coverStrategy:           strings.TrimSpace(snapshot.CoverStrategy),
		manualCoverAssetID:      strings.TrimSpace(snapshot.ManualCoverAssetID),
		coverFrameTimeMs:        snapshot.CoverFrameTimeMs,
		createdAt:               snapshot.CreatedAt.UTC(),
		updatedAt:               snapshot.UpdatedAt.UTC(),
		processedAt:             cloneTime(snapshot.ProcessedAt),
	}
	if err := asset.validate(); err != nil {
		return nil, err
	}
	return asset, nil
}

func (a *MediaAsset) RecordProcessingResult(
	status ProcessingStatus,
	failureReason string,
	now time.Time,
) error {
	if a == nil || a.processingStatus != ProcessingStatusProcessing {
		return fmt.Errorf("%w: only processing assets can receive a processing result", ErrInvalidMediaAssetTransition)
	}
	if status != ProcessingStatusReady && status != ProcessingStatusRejected {
		return fmt.Errorf("%w: processing result must be ready or rejected", ErrInvalidMediaAsset)
	}
	if status == ProcessingStatusRejected && strings.TrimSpace(failureReason) == "" {
		return fmt.Errorf("%w: rejected asset requires failure reason", ErrInvalidMediaAsset)
	}
	if status == ProcessingStatusReady && strings.TrimSpace(failureReason) != "" {
		return fmt.Errorf("%w: ready asset cannot carry failure reason", ErrInvalidMediaAsset)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	processedAt := a.updatedAt
	a.processingStatus = status
	a.processingFailureReason = strings.TrimSpace(failureReason)
	a.processedAt = &processedAt
	return nil
}

func (a *MediaAsset) ChangeAccessPolicy(ownerID string, policy AccessPolicy, now time.Time) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: access policy owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if !validAccessPolicy(policy) {
		return fmt.Errorf("%w: access policy is invalid", ErrInvalidMediaAsset)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.accessPolicy = policy
	return nil
}

func (a *MediaAsset) SelectAutoCover(ownerID string, now time.Time) error {
	if err := a.requireCoverOwner(ownerID); err != nil {
		return err
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = "first_frame"
	a.manualCoverAssetID = ""
	a.coverFrameTimeMs = 0
	return nil
}

func (a *MediaAsset) SelectManualCover(ownerID string, coverAssetID string, frameTimeMs int64, now time.Time) error {
	if err := a.requireCoverOwner(ownerID); err != nil {
		return err
	}
	if strings.TrimSpace(coverAssetID) == "" && frameTimeMs < 0 {
		return fmt.Errorf("%w: manual cover requires a cover asset or non-negative frame", ErrInvalidMediaAsset)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.coverStrategy = "manual"
	a.manualCoverAssetID = strings.TrimSpace(coverAssetID)
	a.coverFrameTimeMs = frameTimeMs
	return nil
}

func (a *MediaAsset) requireCoverOwner(ownerID string) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: cover owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if a.mediaType != "video" || a.processingStatus != ProcessingStatusReady {
		return fmt.Errorf("%w: cover selection requires a ready video asset", ErrInvalidMediaAssetTransition)
	}
	return nil
}

func (a *MediaAsset) Delete(ownerID string, now time.Time) error {
	if a == nil {
		return fmt.Errorf("%w: asset is required", ErrInvalidMediaAsset)
	}
	if strings.TrimSpace(ownerID) != a.ownerID {
		return fmt.Errorf("%w: delete owner does not match", ErrMediaAssetOwnerForbidden)
	}
	if a.processingStatus == ProcessingStatusDeleted {
		return fmt.Errorf("%w: deleted asset cannot be deleted again", ErrInvalidMediaAssetTransition)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	a.processingStatus = ProcessingStatusDeleted
	return nil
}

func (a *MediaAsset) ID() string {
	if a == nil {
		return ""
	}
	return a.id
}

func (a *MediaAsset) Version() int64 {
	if a == nil {
		return 0
	}
	return a.version
}

func (a *MediaAsset) OwnerID() string {
	if a == nil {
		return ""
	}
	return a.ownerID
}

func (a *MediaAsset) SourceSessionID() string {
	if a == nil {
		return ""
	}
	return a.sourceSessionID
}

func (a *MediaAsset) ObjectKey() string {
	if a == nil {
		return ""
	}
	return a.objectKey
}

func (a *MediaAsset) SHA256() string {
	if a == nil {
		return ""
	}
	return a.sha256
}

func (a *MediaAsset) AccessPolicy() AccessPolicy {
	if a == nil {
		return ""
	}
	return a.accessPolicy
}

func (a *MediaAsset) MediaType() string {
	if a == nil {
		return ""
	}
	return a.mediaType
}

func (a *MediaAsset) ContentType() string {
	if a == nil {
		return ""
	}
	return a.contentType
}

func (a *MediaAsset) FileSize() int64 {
	if a == nil {
		return 0
	}
	return a.fileSize
}

func (a *MediaAsset) ProcessingStatus() ProcessingStatus {
	if a == nil {
		return ""
	}
	return a.processingStatus
}

func (a *MediaAsset) CoverStrategy() string {
	if a == nil {
		return ""
	}
	return a.coverStrategy
}

func (a *MediaAsset) ManualCoverAssetID() string {
	if a == nil {
		return ""
	}
	return a.manualCoverAssetID
}

func (a *MediaAsset) CoverFrameTimeMs() int64 {
	if a == nil {
		return 0
	}
	return a.coverFrameTimeMs
}

func (a *MediaAsset) Snapshot() MediaAssetSnapshot {
	if a == nil {
		return MediaAssetSnapshot{}
	}
	return MediaAssetSnapshot{
		ID:                      a.id,
		Version:                 a.version,
		OwnerID:                 a.ownerID,
		SourceSessionID:         a.sourceSessionID,
		ObjectKey:               a.objectKey,
		SHA256:                  a.sha256,
		MediaType:               a.mediaType,
		ContentType:             a.contentType,
		FileSize:                a.fileSize,
		AccessPolicy:            a.accessPolicy,
		ProcessingStatus:        a.processingStatus,
		ProcessingFailureReason: a.processingFailureReason,
		CoverStrategy:           a.coverStrategy,
		ManualCoverAssetID:      a.manualCoverAssetID,
		CoverFrameTimeMs:        a.coverFrameTimeMs,
		CreatedAt:               a.createdAt,
		UpdatedAt:               a.updatedAt,
		ProcessedAt:             cloneTime(a.processedAt),
	}
}

func (a *MediaAsset) validate() error {
	if a == nil ||
		a.id == "" ||
		a.version < 1 ||
		a.ownerID == "" ||
		a.sourceSessionID == "" ||
		a.objectKey == "" ||
		a.sha256 == "" ||
		a.mediaType == "" ||
		a.contentType == "" ||
		a.fileSize <= 0 ||
		(a.coverStrategy != "first_frame" && a.coverStrategy != "manual") ||
		a.coverFrameTimeMs < 0 ||
		!validAccessPolicy(a.accessPolicy) ||
		!validProcessingStatus(a.processingStatus) ||
		a.createdAt.IsZero() ||
		a.updatedAt.IsZero() ||
		a.updatedAt.Before(a.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidMediaAsset)
	}
	switch a.processingStatus {
	case ProcessingStatusProcessing:
		if a.processedAt != nil || a.processingFailureReason != "" {
			return fmt.Errorf("%w: processing asset carries final result", ErrInvalidMediaAsset)
		}
	case ProcessingStatusReady:
		if a.processedAt == nil || a.processingFailureReason != "" {
			return fmt.Errorf("%w: ready asset state is inconsistent", ErrInvalidMediaAsset)
		}
	case ProcessingStatusRejected:
		if a.processedAt == nil || a.processingFailureReason == "" {
			return fmt.Errorf("%w: rejected asset state is inconsistent", ErrInvalidMediaAsset)
		}
	case ProcessingStatusDeleted:
		if a.processingFailureReason != "" {
			return fmt.Errorf("%w: deleted asset carries failure reason", ErrInvalidMediaAsset)
		}
	}
	return nil
}

func (a *MediaAsset) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(a.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidMediaAsset)
	}
	a.version++
	a.updatedAt = now
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

func validAccessPolicy(value AccessPolicy) bool {
	switch value {
	case AccessPolicyOwnerOnly, AccessPolicyReferencedPost, AccessPolicyPublic:
		return true
	default:
		return false
	}
}

func validProcessingStatus(value ProcessingStatus) bool {
	switch value {
	case ProcessingStatusProcessing,
		ProcessingStatusReady,
		ProcessingStatusRejected,
		ProcessingStatusDeleted:
		return true
	default:
		return false
	}
}

func normalizeDigest(value string) string {
	raw := strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
	if raw == "" {
		return ""
	}
	return "sha256:" + raw
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
