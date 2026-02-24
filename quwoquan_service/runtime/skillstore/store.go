package skillstore

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

var (
	ErrSkillNotFound     = errors.New("skill not found")
	ErrInvalidTransition = errors.New("invalid status transition")
	ErrReviewRequired    = errors.New("review required before publishing")
)

// allowed status transitions
var validTransitions = map[SkillStatus][]SkillStatus{
	StatusDraft:     {StatusReview},
	StatusReview:    {StatusApproved, StatusRejected},
	StatusRejected:  {StatusDraft},
	StatusApproved:  {StatusGray, StatusPublished},
	StatusGray:      {StatusPublished, StatusArchived},
	StatusPublished: {StatusArchived, StatusGray},
	StatusArchived:  {StatusDraft},
}

// Store manages skill registrations in MongoDB.
type Store struct {
	coll    *mongo.Collection
	sandbox SandboxConfig
}

func NewStore(db *mongo.Database, sandbox SandboxConfig) *Store {
	return &Store{
		coll:    db.Collection("skill_store"),
		sandbox: sandbox,
	}
}

func (s *Store) EnsureIndexes(ctx context.Context) error {
	_, err := s.coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "skillId", Value: 1}, {Key: "version", Value: 1}},
		Options: options.Index().SetUnique(true),
	})
	return err
}

// Register creates a new skill registration in draft status.
func (s *Store) Register(ctx context.Context, reg SkillRegistration) error {
	reg.Status = StatusDraft
	reg.CreatedAt = time.Now().UTC()
	reg.UpdatedAt = reg.CreatedAt
	_, err := s.coll.InsertOne(ctx, reg)
	return err
}

// Get retrieves a skill registration.
func (s *Store) Get(ctx context.Context, skillID, version string) (*SkillRegistration, error) {
	var reg SkillRegistration
	err := s.coll.FindOne(ctx, bson.M{"skillId": skillID, "version": version}).Decode(&reg)
	if err == mongo.ErrNoDocuments {
		return nil, ErrSkillNotFound
	}
	return &reg, err
}

// List returns skills matching optional filters.
func (s *Store) List(ctx context.Context, provider string, status SkillStatus) ([]SkillRegistration, error) {
	filter := bson.M{}
	if provider != "" {
		filter["provider"] = provider
	}
	if status != "" {
		filter["status"] = status
	}

	cursor, err := s.coll.Find(ctx, filter)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var results []SkillRegistration
	if err := cursor.All(ctx, &results); err != nil {
		return nil, err
	}
	return results, nil
}

// Transition moves a skill to a new status with validation.
func (s *Store) Transition(ctx context.Context, skillID, version string, newStatus SkillStatus) error {
	reg, err := s.Get(ctx, skillID, version)
	if err != nil {
		return err
	}

	if !isValidTransition(reg.Status, newStatus) {
		return fmt.Errorf("%w: %s → %s", ErrInvalidTransition, reg.Status, newStatus)
	}

	update := bson.M{
		"$set": bson.M{
			"status":    newStatus,
			"updatedAt": time.Now().UTC(),
		},
	}

	if newStatus == StatusPublished {
		now := time.Now().UTC()
		update["$set"].(bson.M)["publishedAt"] = now
	}

	_, err = s.coll.UpdateOne(ctx,
		bson.M{"skillId": skillID, "version": version},
		update,
	)
	return err
}

// SubmitReview records a review decision and triggers auto-checks.
func (s *Store) SubmitReview(ctx context.Context, skillID, version string, review ReviewRecord) error {
	reg, err := s.Get(ctx, skillID, version)
	if err != nil {
		return err
	}
	if reg.Status != StatusReview {
		return fmt.Errorf("%w: skill must be in review status", ErrInvalidTransition)
	}

	review.AutoChecks = s.runAutoChecks(reg)
	review.ReviewedAt = time.Now().UTC()

	update := bson.M{
		"$set": bson.M{
			"status":    review.Decision,
			"review":    review,
			"updatedAt": time.Now().UTC(),
		},
	}

	_, err = s.coll.UpdateOne(ctx,
		bson.M{"skillId": skillID, "version": version},
		update,
	)
	return err
}

// SetGrayConfig configures gray release for an approved skill.
func (s *Store) SetGrayConfig(ctx context.Context, skillID, version string, cfg GrayConfig) error {
	cfg.StartedAt = time.Now().UTC()
	_, err := s.coll.UpdateOne(ctx,
		bson.M{"skillId": skillID, "version": version},
		bson.M{
			"$set": bson.M{
				"status":     StatusGray,
				"grayConfig": cfg,
				"updatedAt":  time.Now().UTC(),
			},
		},
	)
	return err
}

// UpdateMetrics increments usage metrics for a published skill.
func (s *Store) UpdateMetrics(ctx context.Context, skillID, version string, success bool, latencyMs float64) error {
	inc := bson.M{"metrics.totalCalls": 1}
	set := bson.M{"updatedAt": time.Now().UTC()}

	_, err := s.coll.UpdateOne(ctx,
		bson.M{"skillId": skillID, "version": version},
		bson.M{"$inc": inc, "$set": set},
	)
	return err
}

// GetSandboxConfig returns the sandbox config for ecosystem skills.
func (s *Store) GetSandboxConfig() SandboxConfig {
	return s.sandbox
}

func (s *Store) runAutoChecks(reg *SkillRegistration) []AutoCheck {
	var checks []AutoCheck

	// Check context requirements are not excessive
	contextOK := len(reg.Manifest.ContextRequirements) <= 3
	checks = append(checks, AutoCheck{
		Name:   "context_scope_reasonable",
		Passed: contextOK,
		Detail: fmt.Sprintf("requires %d context dimensions", len(reg.Manifest.ContextRequirements)),
	})

	// Check tool dependencies are declared
	toolsOK := len(reg.Manifest.ToolDependencies) <= 10
	checks = append(checks, AutoCheck{
		Name:   "tool_dependencies_bounded",
		Passed: toolsOK,
		Detail: fmt.Sprintf("depends on %d tools", len(reg.Manifest.ToolDependencies)),
	})

	// Check data class is not too permissive for ecosystem
	dataClassOK := true
	if reg.Provider == "ecosystem" && reg.Manifest.DataClassMax == "SENSITIVE" {
		dataClassOK = false
	}
	checks = append(checks, AutoCheck{
		Name:   "data_class_policy",
		Passed: dataClassOK,
		Detail: fmt.Sprintf("dataClassMax=%s, provider=%s", reg.Manifest.DataClassMax, reg.Provider),
	})

	return checks
}

func isValidTransition(from, to SkillStatus) bool {
	targets, ok := validTransitions[from]
	if !ok {
		return false
	}
	for _, t := range targets {
		if t == to {
			return true
		}
	}
	return false
}
