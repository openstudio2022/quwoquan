package model

import "time"

type Item struct {
	AccountID     string     `json:"-" bson:"accountId"`
	TaskID        string     `json:"taskId" bson:"taskId"`
	Title         string     `json:"title" bson:"title"`
	Description   string     `json:"description,omitempty" bson:"description,omitempty"`
	Status        string     `json:"status" bson:"status"`
	DueAt         *time.Time `json:"dueAt,omitempty" bson:"dueAt,omitempty"`
	Priority      string     `json:"priority,omitempty" bson:"priority,omitempty"`
	SourceSkillID string     `json:"sourceSkillId,omitempty" bson:"sourceSkillId,omitempty"`
	UpdatedAt     time.Time  `json:"updatedAt" bson:"updatedAt"`
}

type Slice struct {
	Items []Item `json:"items"`
}
