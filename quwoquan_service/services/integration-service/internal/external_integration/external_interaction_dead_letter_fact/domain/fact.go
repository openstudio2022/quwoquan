package domain

import (
	"fmt"
	"strings"
	"time"
)

// Fact 是任务首次进入 dead 终态时形成的不可变事实。恢复命令只改变任务状态，
// 不删除或重写已经发生的死信事实。
type Fact struct {
	DeadLetterID   string    `bson:"_id" json:"deadLetterId"`
	TaskID         string    `bson:"taskId" json:"taskId"`
	RequestID      string    `bson:"requestId" json:"requestId"`
	Operation      string    `bson:"operation" json:"operation"`
	Provider       string    `bson:"provider" json:"provider"`
	FinalError     string    `bson:"finalError" json:"finalError"`
	Retryable      bool      `bson:"retryable" json:"retryable"`
	RecoveryAction string    `bson:"recoveryAction" json:"recoveryAction"`
	CreatedAt      time.Time `bson:"createdAt" json:"createdAt"`
}

func NewFact(fact Fact) (Fact, error) {
	fact.DeadLetterID = strings.TrimSpace(fact.DeadLetterID)
	fact.TaskID = strings.TrimSpace(fact.TaskID)
	fact.RequestID = strings.TrimSpace(fact.RequestID)
	fact.Operation = strings.TrimSpace(fact.Operation)
	fact.Provider = strings.TrimSpace(fact.Provider)
	fact.FinalError = strings.TrimSpace(fact.FinalError)
	fact.RecoveryAction = strings.TrimSpace(fact.RecoveryAction)
	fact.CreatedAt = fact.CreatedAt.UTC()
	if fact.DeadLetterID == "" || fact.TaskID == "" || fact.RequestID == "" {
		return Fact{}, fmt.Errorf("deadLetterId, taskId and requestId are required")
	}
	if fact.Operation == "" || fact.Provider == "" {
		return Fact{}, fmt.Errorf("operation and provider are required")
	}
	if fact.FinalError == "" || fact.RecoveryAction == "" || fact.CreatedAt.IsZero() {
		return Fact{}, fmt.Errorf("finalError, recoveryAction and createdAt are required")
	}
	return fact, nil
}
