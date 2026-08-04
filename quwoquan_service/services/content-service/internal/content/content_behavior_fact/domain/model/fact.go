package model

import (
	"fmt"
	"strings"
	"time"
)

// Fact is the immutable persisted form of one accepted content behavior.
// ClientEventID is scoped by the trusted business actor in UserID.
type Fact struct {
	ClientEventID     string   `bson:"clientEventId,omitempty"`
	State             string   `bson:"state,omitempty"`
	UserID            string   `bson:"userId"`
	PersonaID         string   `bson:"personaId,omitempty"`
	DeviceActorID     string   `bson:"deviceActorId,omitempty"`
	SessionID         string   `bson:"sessionId"`
	FeedSessionID     string   `bson:"feedSessionId,omitempty"`
	PlaybackSessionID string   `bson:"playbackSessionId,omitempty"`
	PageVisitID       string   `bson:"pageVisitId,omitempty"`
	ContentID         string   `bson:"contentId"`
	Action            string   `bson:"action"`
	ContentType       string   `bson:"contentType,omitempty"`
	ObjectID          string   `bson:"objectId,omitempty"`
	ObjectKind        string   `bson:"objectKind,omitempty"`
	DisplayName       string   `bson:"displayName,omitempty"`
	SourceSurface     string   `bson:"sourceSurface,omitempty"`
	TaxonomyReleaseID string   `bson:"taxonomyReleaseId,omitempty"`
	Tags              []string `bson:"tagRefs,omitempty"`
	Duration          float64  `bson:"duration,omitempty"`
	AuthorID          string   `bson:"authorId,omitempty"`
	// ImpactHelpType is derived only after Content resolves the authoritative
	// Post author/action boundary. It is never accepted from the public payload.
	ImpactHelpType         string    `bson:"impactHelpType,omitempty"`
	ReferralSource         string    `bson:"referralSource,omitempty"`
	EngagementDepth        int       `bson:"engagementDepth,omitempty"`
	ConsumedRatio          float64   `bson:"consumedRatio,omitempty"`
	TotalUnits             int       `bson:"totalUnits,omitempty"`
	EffectivePlayMS        int       `bson:"effectivePlayMs,omitempty"`
	EntityRefs             []string  `bson:"entityRefs,omitempty"`
	FeedRequestID          string    `bson:"feedRequestId,omitempty"`
	Position               int       `bson:"position,omitempty"`
	CommentLength          int       `bson:"commentLength,omitempty"`
	ChannelID              string    `bson:"channelId,omitempty"`
	PolicyDigest           string    `bson:"policyDigest,omitempty"`
	RecallPath             string    `bson:"recallPath,omitempty"`
	ContentVertical        string    `bson:"contentVertical,omitempty"`
	SupplySource           string    `bson:"supplySource,omitempty"`
	IntersectionDimension  string    `bson:"intersectionDimension,omitempty"`
	IntersectionTagRefs    []string  `bson:"intersectionTagRefs,omitempty"`
	IntersectionID         string    `bson:"intersectionId,omitempty"`
	IntersectionClass      string    `bson:"intersectionClass,omitempty"`
	IntersectionSourceRef  string    `bson:"intersectionSourceRef,omitempty"`
	IntersectionEvidenceID string    `bson:"intersectionEvidenceId,omitempty"`
	SubjectID              string    `bson:"subjectId,omitempty"`
	FeedbackKind           string    `bson:"feedbackKind,omitempty"`
	MotionDirection        string    `bson:"direction,omitempty"`
	MotionProfile          string    `bson:"motionProfile,omitempty"`
	SettleMS               *int      `bson:"settleMs,omitempty"`
	ReducedMotion          *bool     `bson:"reducedMotion,omitempty"`
	Committed              *bool     `bson:"committed,omitempty"`
	OccurredAt             string    `bson:"occurredAt"`
	CreatedAt              time.Time `bson:"createdAt"`
}

func (fact Fact) Validate() error {
	if strings.TrimSpace(fact.ClientEventID) == "" ||
		strings.TrimSpace(fact.UserID) == "" ||
		strings.TrimSpace(fact.SessionID) == "" ||
		strings.TrimSpace(fact.Action) == "" ||
		strings.TrimSpace(fact.OccurredAt) == "" ||
		fact.CreatedAt.IsZero() {
		return fmt.Errorf("ContentBehaviorFact requires client event, trusted actor, session, action and timestamps")
	}
	if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(fact.OccurredAt)); err != nil {
		return fmt.Errorf("ContentBehaviorFact occurredAt is invalid: %w", err)
	}
	return nil
}
