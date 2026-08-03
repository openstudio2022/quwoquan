package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip guide assignment")
	ErrPermissionDenied = errors.New("trip guide assignment permission denied")
	ErrRevisionConflict = errors.New("trip guide assignment revision conflict")
	ErrStateInvalid     = errors.New("trip guide assignment state invalid")
)

type Role string
type TaskKind string
type AttributionKind string
type Status string

const (
	RoleLeader         Role = "leader"
	RoleAssistantGuide Role = "assistant_guide"
	RoleLicensedGuide  Role = "licensed_guide"
	RoleLocalExpert    Role = "local_expert"

	TaskCollection     TaskKind = "collection"
	TaskBriefing       TaskKind = "briefing"
	TaskRouteGuidance  TaskKind = "route_guidance"
	TaskCommentary     TaskKind = "commentary"
	TaskGeneralSupport TaskKind = "general_support"

	AttributionAdministrative         AttributionKind = "administrative"
	AttributionGeneralFact            AttributionKind = "general_fact"
	AttributionProfessionalCommentary AttributionKind = "professional_commentary"

	StatusAssigned   Status = "assigned"
	StatusAccepted   Status = "accepted"
	StatusInProgress Status = "in_progress"
	StatusCompleted  Status = "completed"
	StatusCancelled  Status = "cancelled"
)

type Assignment struct {
	AssignmentID                 string          `json:"id" bson:"_id"`
	Version                      int64           `json:"version" bson:"version"`
	TripID                       string          `json:"tripId" bson:"tripId"`
	TaskKey                      string          `json:"taskKey" bson:"taskKey"`
	AssigneePersonaID            string          `json:"assigneePersonaId" bson:"assigneePersonaId"`
	Role                         Role            `json:"role" bson:"role"`
	TaskKind                     TaskKind        `json:"taskKind" bson:"taskKind"`
	Title                        string          `json:"title" bson:"title"`
	DueAt                        *time.Time      `json:"dueAt,omitempty" bson:"dueAt,omitempty"`
	SourceRevisionNumber         int64           `json:"sourceRevisionNumber" bson:"sourceRevisionNumber"`
	AttributionKind              AttributionKind `json:"attributionKind" bson:"attributionKind"`
	AttributionPersonaID         string          `json:"attributionPersonaId" bson:"attributionPersonaId"`
	PublicQualificationPersonaID string          `json:"publicQualificationPersonaId,omitempty" bson:"publicQualificationPersonaId,omitempty"`
	Status                       Status          `json:"status" bson:"status"`
	CreatedByPersonaID           string          `json:"createdByPersonaId" bson:"createdByPersonaId"`
	CreatedAt                    time.Time       `json:"createdAt" bson:"createdAt"`
	UpdatedAt                    time.Time       `json:"updatedAt" bson:"updatedAt"`
}

type PutInput struct {
	AssigneePersonaID            string
	Role                         Role
	TaskKind                     TaskKind
	Title                        string
	DueAt                        *time.Time
	SourceRevisionNumber         int64
	AttributionKind              AttributionKind
	AttributionPersonaID         string
	PublicQualificationPersonaID string
}

func Create(id, tripID, taskKey, creatorPersonaID string, input PutInput, now time.Time) (Assignment, error) {
	assignment := Assignment{
		AssignmentID: strings.TrimSpace(id), Version: 1, TripID: strings.TrimSpace(tripID),
		TaskKey: strings.TrimSpace(taskKey), Status: StatusAssigned,
		CreatedByPersonaID: strings.TrimSpace(creatorPersonaID), CreatedAt: now.UTC(), UpdatedAt: now.UTC(),
	}
	apply(&assignment, input)
	if err := assignment.Validate(); err != nil {
		return Assignment{}, err
	}
	return assignment, nil
}

func (assignment Assignment) Put(expectedVersion int64, input PutInput, now time.Time) (Assignment, error) {
	if expectedVersion != assignment.Version {
		return Assignment{}, ErrRevisionConflict
	}
	if assignment.Status == StatusCompleted || input.SourceRevisionNumber < assignment.SourceRevisionNumber {
		return Assignment{}, ErrStateInvalid
	}
	next := assignment
	next.Version++
	next.Status = StatusAssigned
	next.UpdatedAt = now.UTC()
	apply(&next, input)
	if err := next.Validate(); err != nil {
		return Assignment{}, err
	}
	return next, nil
}

func (assignment Assignment) Transition(expectedVersion int64, target Status, now time.Time) (Assignment, error) {
	if expectedVersion != assignment.Version {
		return Assignment{}, ErrRevisionConflict
	}
	if !validTransition(assignment.Status, target) {
		return Assignment{}, ErrStateInvalid
	}
	next := assignment
	next.Version++
	next.Status = target
	next.UpdatedAt = now.UTC()
	return next, next.Validate()
}

func apply(assignment *Assignment, input PutInput) {
	assignment.AssigneePersonaID = strings.TrimSpace(input.AssigneePersonaID)
	assignment.Role = input.Role
	assignment.TaskKind = input.TaskKind
	assignment.Title = strings.TrimSpace(input.Title)
	assignment.DueAt = cloneTime(input.DueAt)
	assignment.SourceRevisionNumber = input.SourceRevisionNumber
	assignment.AttributionKind = input.AttributionKind
	assignment.AttributionPersonaID = strings.TrimSpace(input.AttributionPersonaID)
	assignment.PublicQualificationPersonaID = strings.TrimSpace(input.PublicQualificationPersonaID)
}

func (assignment Assignment) Validate() error {
	if assignment.AssignmentID == "" || assignment.Version <= 0 || assignment.TripID == "" ||
		assignment.TaskKey == "" || assignment.AssigneePersonaID == "" || !assignment.Role.Valid() ||
		!assignment.TaskKind.Valid() || assignment.Title == "" || len([]rune(assignment.Title)) > 160 ||
		assignment.SourceRevisionNumber <= 0 || !assignment.AttributionKind.Valid() ||
		assignment.AttributionPersonaID == "" || !assignment.Status.Valid() || assignment.CreatedByPersonaID == "" ||
		assignment.CreatedAt.IsZero() || assignment.UpdatedAt.IsZero() ||
		assignment.AttributionKind == AttributionProfessionalCommentary && assignment.AttributionPersonaID != assignment.AssigneePersonaID ||
		assignment.Role == RoleLicensedGuide && assignment.PublicQualificationPersonaID != assignment.AssigneePersonaID ||
		assignment.Role != RoleLicensedGuide && assignment.PublicQualificationPersonaID != "" {
		return ErrInvalidArgument
	}
	return nil
}

func (role Role) Valid() bool {
	return role == RoleLeader || role == RoleAssistantGuide || role == RoleLicensedGuide || role == RoleLocalExpert
}
func (kind TaskKind) Valid() bool {
	return kind == TaskCollection || kind == TaskBriefing || kind == TaskRouteGuidance || kind == TaskCommentary || kind == TaskGeneralSupport
}
func (kind AttributionKind) Valid() bool {
	return kind == AttributionAdministrative || kind == AttributionGeneralFact || kind == AttributionProfessionalCommentary
}
func (status Status) Valid() bool {
	return status == StatusAssigned || status == StatusAccepted || status == StatusInProgress || status == StatusCompleted || status == StatusCancelled
}

func validTransition(current, target Status) bool {
	switch current {
	case StatusAssigned:
		return target == StatusAccepted || target == StatusCancelled
	case StatusAccepted:
		return target == StatusInProgress || target == StatusCancelled
	case StatusInProgress:
		return target == StatusCompleted || target == StatusCancelled
	default:
		return false
	}
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	copy := value.UTC()
	return &copy
}
