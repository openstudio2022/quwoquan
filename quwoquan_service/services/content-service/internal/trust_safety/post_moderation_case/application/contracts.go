package moderation

import (
	"context"
	"time"

	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

type OpenPostModerationCaseCommand struct {
	PostID        string
	PostVersion   int64
	ContentDigest string
}

type ReviewPostModerationCaseCommand struct {
	PostID     string
	CaseID     string
	ReviewerID string
}

type DecidePostModerationCaseCommand struct {
	PostID         string
	CaseID         string
	ReviewerID     string
	Decision       moderationmodel.Decision
	DecisionReason string
}

type SupersedePostModerationCaseCommand struct {
	PostID string
	CaseID string
}

type GetPostPublicationEligibilityQuery struct {
	PostID        string
	PostVersion   int64
	ContentDigest string
}

type GetCurrentPostModerationCaseQuery struct {
	PostID string
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

type PostModerationCaseOpsSlice struct {
	ID             string                 `json:"id"`
	Version        int64                  `json:"version"`
	PostID         string                 `json:"postId"`
	PostVersion    int64                  `json:"postVersion"`
	ContentDigest  string                 `json:"contentDigest"`
	Status         moderationmodel.Status `json:"status"`
	ReviewerID     string                 `json:"reviewerId,omitempty"`
	DecisionReason string                 `json:"decisionReason,omitempty"`
	CreatedAt      time.Time              `json:"createdAt"`
	UpdatedAt      time.Time              `json:"updatedAt"`
	DecidedAt      *time.Time             `json:"decidedAt,omitempty"`
}

type CurrentPostModerationCaseReader interface {
	FindCurrentByPostID(
		ctx context.Context,
		postID string,
	) (PostModerationCaseOpsSlice, bool, error)
}

type PublicationEligibilityApplicationReader interface {
	GetPostPublicationEligibility(
		ctx context.Context,
		query GetPostPublicationEligibilityQuery,
	) (PublicationEligibilitySlice, error)
}
