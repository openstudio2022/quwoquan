package runruntime

import "time"

// SkillActivityEvent is the redacted AssistantRun activity boundary consumed
// by SkillActivityView. It deliberately excludes the request text, answer,
// context snapshot, tool payloads, evidence bodies, and presentation data.
type SkillActivityEvent struct {
	RunID       string
	UserID      string
	SkillID     string
	State       string
	FailureCode string
	Revision    int64
	OccurredAt  time.Time
}
