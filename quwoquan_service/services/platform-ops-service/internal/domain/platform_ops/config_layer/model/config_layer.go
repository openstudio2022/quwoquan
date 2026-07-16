package model

import (
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalid             = errors.New("invalid config layer")
	ErrNotFound            = errors.New("config layer not found")
	ErrVersionConflict     = errors.New("config layer version conflict")
	ErrIdempotencyConflict = errors.New("config layer idempotency conflict")
)

const maxConfigEntries = 256

type ValueKind string

const (
	ValueKindString ValueKind = "string"
	ValueKindInt    ValueKind = "int"
	ValueKindFloat  ValueKind = "float"
	ValueKindBool   ValueKind = "bool"
)

type ConfigValue struct {
	Kind        ValueKind `json:"kind"`
	StringValue *string   `json:"stringValue,omitempty"`
	IntValue    *int64    `json:"intValue,omitempty"`
	FloatValue  *float64  `json:"floatValue,omitempty"`
	BoolValue   *bool     `json:"boolValue,omitempty"`
}

func (v ConfigValue) Validate(expected ValueKind) error {
	if v.Kind != expected {
		return fmt.Errorf("config value kind %q does not match catalog kind %q", v.Kind, expected)
	}
	setCount := 0
	for _, set := range []bool{
		v.StringValue != nil,
		v.IntValue != nil,
		v.FloatValue != nil,
		v.BoolValue != nil,
	} {
		if set {
			setCount++
		}
	}
	if setCount != 1 {
		return errors.New("config value must set exactly one typed value")
	}
	switch v.Kind {
	case ValueKindString:
		if v.StringValue == nil {
			return errors.New("string config requires stringValue")
		}
	case ValueKindInt:
		if v.IntValue == nil {
			return errors.New("int config requires intValue")
		}
	case ValueKindFloat:
		if v.FloatValue == nil {
			return errors.New("float config requires floatValue")
		}
	case ValueKindBool:
		if v.BoolValue == nil {
			return errors.New("bool config requires boolValue")
		}
	default:
		return fmt.Errorf("unsupported config value kind %q", v.Kind)
	}
	return nil
}

type ConfigEntry struct {
	Key   string      `json:"key"`
	Value ConfigValue `json:"value"`
}

type Scope struct {
	Level       string `json:"scopeLevel"`
	ID          string `json:"scopeId"`
	Environment string `json:"environment,omitempty"`
	Cluster     string `json:"cluster,omitempty"`
	Service     string `json:"service,omitempty"`
}

func (s Scope) Validate() error {
	s = s.Normalized()
	if s.ID == "" {
		return errors.New("config scopeId is required")
	}
	switch s.Level {
	case "global":
		if s.ID != "all" || s.Environment != "" || s.Cluster != "" || s.Service != "" {
			return errors.New("global scope must use scopeId=all without environment, cluster or service")
		}
	case "environment":
		if s.Environment == "" || s.ID != s.Environment || s.Cluster != "" || s.Service != "" {
			return errors.New("environment scope must bind scopeId to environment only")
		}
	case "cluster":
		if s.Environment == "" || s.Cluster == "" || s.ID != s.Cluster || s.Service != "" {
			return errors.New("cluster scope requires environment and matching cluster scopeId")
		}
	case "service":
		if s.Environment == "" || s.Cluster == "" || s.Service == "" || s.ID != s.Service {
			return errors.New("service scope requires environment, cluster and matching service scopeId")
		}
	default:
		return fmt.Errorf("unsupported config scopeLevel %q", s.Level)
	}
	return nil
}

func (s Scope) Normalized() Scope {
	s.Level = strings.TrimSpace(s.Level)
	s.ID = strings.TrimSpace(s.ID)
	s.Environment = strings.TrimSpace(s.Environment)
	s.Cluster = strings.TrimSpace(s.Cluster)
	s.Service = strings.TrimSpace(s.Service)
	return s
}

func (s Scope) LayerID() string {
	s = s.Normalized()
	switch s.Level {
	case "global":
		return "global:all"
	case "environment":
		return "environment:" + s.Environment
	case "cluster":
		return strings.Join([]string{"cluster", s.Environment, s.Cluster}, ":")
	case "service":
		return strings.Join([]string{"service", s.Environment, s.Cluster, s.Service}, ":")
	default:
		return s.Level + ":" + s.ID
	}
}

type ConfigLayer struct {
	ID        string        `json:"id"`
	Version   int64         `json:"version"`
	Scope     Scope         `json:"scope"`
	Entries   []ConfigEntry `json:"entries"`
	Status    string        `json:"status"`
	CreatedAt string        `json:"createdAt"`
	UpdatedAt string        `json:"updatedAt"`
}

type Event struct {
	ID            string
	Type          string
	AggregateID   string
	AggregateType string
	Payload       []byte
	OccurredAt    time.Time
}

func NewConfigLayer(scope Scope, now time.Time) (ConfigLayer, error) {
	scope = scope.Normalized()
	if err := scope.Validate(); err != nil {
		return ConfigLayer{}, err
	}
	timestamp := now.UTC().Format(time.RFC3339)
	return ConfigLayer{
		ID: scope.LayerID(), Version: 0, Scope: scope, Entries: []ConfigEntry{},
		Status: "active", CreatedAt: timestamp, UpdatedAt: timestamp,
	}, nil
}

func (l ConfigLayer) Validate() error {
	if err := l.Scope.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(l.ID) == "" || l.ID != l.Scope.LayerID() {
		return errors.New("config layer id must equal canonical scope id")
	}
	if l.Version < 0 {
		return errors.New("config layer version cannot be negative")
	}
	if l.Status != "active" && l.Status != "retired" {
		return fmt.Errorf("unsupported config layer status %q", l.Status)
	}
	if len(l.Entries) > maxConfigEntries {
		return fmt.Errorf("config layer exceeds %d entries", maxConfigEntries)
	}
	seen := make(map[string]struct{}, len(l.Entries))
	for _, entry := range l.Entries {
		key := strings.TrimSpace(entry.Key)
		if key == "" {
			return errors.New("config entry key is required")
		}
		if _, exists := seen[key]; exists {
			return fmt.Errorf("duplicate config entry %q", key)
		}
		seen[key] = struct{}{}
		if err := entry.Value.Validate(entry.Value.Kind); err != nil {
			return fmt.Errorf("config entry %q: %w", key, err)
		}
	}
	createdAt, err := time.Parse(time.RFC3339, l.CreatedAt)
	if err != nil {
		return fmt.Errorf("config layer createdAt must be RFC3339: %w", err)
	}
	updatedAt, err := time.Parse(time.RFC3339, l.UpdatedAt)
	if err != nil {
		return fmt.Errorf("config layer updatedAt must be RFC3339: %w", err)
	}
	if updatedAt.Before(createdAt) {
		return errors.New("config layer updatedAt cannot precede createdAt")
	}
	return nil
}

func (l ConfigLayer) SetValue(
	key string,
	value ConfigValue,
	expectedKind ValueKind,
	expectedScope string,
	now time.Time,
) (ConfigLayer, error) {
	if l.Status != "active" {
		return ConfigLayer{}, errors.New("retired config layer cannot be modified")
	}
	key = strings.TrimSpace(key)
	if key == "" {
		return ConfigLayer{}, errors.New("config key is required")
	}
	if strings.TrimSpace(expectedScope) != l.Scope.Level {
		return ConfigLayer{}, fmt.Errorf("config key scope %q cannot be written to %q layer", expectedScope, l.Scope.Level)
	}
	if err := value.Validate(expectedKind); err != nil {
		return ConfigLayer{}, err
	}
	next := l
	next.Entries = append([]ConfigEntry(nil), l.Entries...)
	found := false
	for index := range next.Entries {
		if next.Entries[index].Key == key {
			next.Entries[index].Value = value
			found = true
			break
		}
	}
	if !found {
		if len(next.Entries) >= maxConfigEntries {
			return ConfigLayer{}, fmt.Errorf("config layer exceeds %d entries", maxConfigEntries)
		}
		next.Entries = append(next.Entries, ConfigEntry{Key: key, Value: value})
	}
	sort.Slice(next.Entries, func(i, j int) bool { return next.Entries[i].Key < next.Entries[j].Key })
	next.Version++
	next.UpdatedAt = now.UTC().Format(time.RFC3339)
	return next, next.Validate()
}
