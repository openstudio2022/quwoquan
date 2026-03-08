package model

import "time"

type Report struct {
	ID          string     `json:"id" db:"id"`
	ReporterID  string     `json:"reporterId" db:"reporter_id"`
	TargetType  string     `json:"targetType" db:"target_type"`
	TargetID    string     `json:"targetId" db:"target_id"`
	Reason      string     `json:"reason" db:"reason"`
	Description string     `json:"description,omitempty" db:"description"`
	Status      string     `json:"status" db:"status"`
	ReviewerID  string     `json:"reviewerId,omitempty" db:"reviewer_id"`
	Resolution  string     `json:"resolution,omitempty" db:"resolution"`
	CreatedAt   time.Time  `json:"createdAt" db:"created_at"`
	ResolvedAt  *time.Time `json:"resolvedAt,omitempty" db:"resolved_at"`
}
