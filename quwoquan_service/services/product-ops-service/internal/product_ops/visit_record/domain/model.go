package domain

import (
	"errors"
	"strings"
	"time"
	"unicode/utf8"
)

var ErrInvalid = errors.New("invalid visit input")

const maxTargetKeyLength = 256

var supportedTargetTypes = map[string]struct{}{
	"page": {}, "post": {}, "circle": {}, "user": {},
}

// RecordVisitCommand is the object-owned command after the HTTP boundary has
// derived the trusted actor. It is not the public wire request: UserID can
// only be supplied by the inbound adapter.
type RecordVisitCommand struct {
	UserID     string `json:"userId"`
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
}

func (input RecordVisitCommand) Normalize() RecordVisitCommand {
	input.UserID = strings.TrimSpace(input.UserID)
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.TargetKey = strings.TrimSpace(input.TargetKey)
	return input
}

func (input RecordVisitCommand) Validate() error {
	input = input.Normalize()
	if input.UserID == "" || input.TargetKey == "" ||
		utf8.RuneCountInString(input.TargetKey) > maxTargetKeyLength {
		return ErrInvalid
	}
	if _, supported := supportedTargetTypes[input.TargetType]; !supported {
		return ErrInvalid
	}
	return nil
}

type VisitRecord struct {
	TargetType string    `json:"targetType" bson:"targetType"`
	TargetKey  string    `json:"targetKey" bson:"targetKey"`
	UserID     string    `json:"-" bson:"userId"`
	VisitCount int       `json:"visitCount" bson:"visitCount"`
	OccurredAt time.Time `json:"occurredAt" bson:"occurredAt"`
}

type VisitStatsQuery struct {
	TargetType string
	TargetKey  string
}

func (query VisitStatsQuery) NormalizeAndValidate() (VisitStatsQuery, error) {
	query.TargetType = strings.TrimSpace(query.TargetType)
	query.TargetKey = strings.TrimSpace(query.TargetKey)
	if query.TargetType != "" {
		if _, supported := supportedTargetTypes[query.TargetType]; !supported {
			return VisitStatsQuery{}, ErrInvalid
		}
	}
	return query, nil
}

type VisitStats struct {
	TotalVisits int           `json:"totalVisits"`
	Items       []VisitRecord `json:"items"`
}
