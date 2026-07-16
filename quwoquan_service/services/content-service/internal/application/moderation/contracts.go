package moderation

import (
	"context"
	"time"

	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
)

type OpenPostModerationCaseCommand struct {
	PostID        string
	PostVersion   int64
	ContentDigest string
}

type ReviewPostModerationCaseCommand struct {
	CaseID     string
	ReviewerID string
}

type DecidePostModerationCaseCommand struct {
	CaseID         string
	ReviewerID     string
	Decision       moderationmodel.Decision
	DecisionReason string
}

type SupersedePostModerationCaseCommand struct {
	CaseID string
}

type GetPostPublicationEligibilityQuery struct {
	PostID        string
	PostVersion   int64
	ContentDigest string
}

type PostModerationCaseCommandResult struct {
	CaseID   string
	Version  int64
	Status   moderationmodel.Status
	Replayed bool
}

// PublicationEligibilitySlice is the typed application read result consumed by
// the future Post lifecycle adapter. It intentionally contains no raw BSON.
type PublicationEligibilitySlice struct {
	Eligible      bool
	CaseID        string
	CaseVersion   int64
	Moderation    moderationmodel.Status
	CheckedAt     time.Time
	DecisionAt    *time.Time
	FailureReason string
}

type PublicationEligibilityApplicationReader interface {
	GetPostPublicationEligibility(
		ctx context.Context,
		query GetPostPublicationEligibilityQuery,
	) (PublicationEligibilitySlice, error)
}
