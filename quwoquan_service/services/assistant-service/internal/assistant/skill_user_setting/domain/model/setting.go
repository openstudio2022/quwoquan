// Package model 定义 SkillUserSetting 聚合和唯一 PUT 命令语义。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"
)

const (
	StatusEnabled  = "enabled"
	StatusDisabled = "disabled"

	MemoryPackageDefault    = "package_default"
	MemoryConfirmBeforeSave = "confirm_before_save"
	MemoryDisabled          = "disabled"

	CommandPut   = "PutSkillUserSetting"
	EventChanged = "SkillUserSettingChanged"
)

var (
	ErrInvalidArgument     = errors.New("skill user setting command is invalid")
	ErrNotFound            = errors.New("skill user setting is not found")
	ErrRevisionConflict    = errors.New("skill user setting revision conflict")
	ErrIdempotencyConflict = errors.New("skill user setting idempotency conflict")
	ErrSchemaMismatch      = errors.New("skill user setting schema digest mismatch")
	ErrPackageUnavailable  = errors.New("skill user setting package is unavailable")
	ErrStorageUnavailable  = errors.New("skill user setting storage is unavailable")
)

type Setting struct {
	ID                        string          `json:"id"`
	AccountID                 string          `json:"accountId"`
	SkillID                   string          `json:"skillId"`
	Status                    string          `json:"status"`
	ConfigurationData         json.RawMessage `json:"configurationData"`
	ConfigurationSchemaDigest string          `json:"configurationSchemaDigest"`
	MemoryPolicy              string          `json:"memoryPolicy"`
	ConnectorConnectionRefs   []string        `json:"connectorConnectionRefs"`
	Revision                  int64           `json:"revision"`
	CreatedAt                 time.Time       `json:"createdAt"`
	UpdatedAt                 time.Time       `json:"updatedAt"`
}

type PutInput struct {
	AccountID                 string
	SkillID                   string
	Status                    string
	ConfigurationData         json.RawMessage
	ConfigurationSchemaDigest string
	MemoryPolicy              string
	ConnectorConnectionRefs   []string
	ExpectedRevision          int64
	IdempotencyKey            string
	OccurredAt                time.Time
}

type Command struct {
	PutInput
	RequestDigest string
}

type MutationResult struct {
	Setting  Setting `json:"setting"`
	Changed  bool    `json:"changed"`
	Replayed bool    `json:"replayed"`
}

func NewPutCommand(input PutInput) (Command, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.SkillID = strings.TrimSpace(input.SkillID)
	input.Status = strings.TrimSpace(input.Status)
	input.ConfigurationSchemaDigest = strings.TrimSpace(input.ConfigurationSchemaDigest)
	input.MemoryPolicy = strings.TrimSpace(input.MemoryPolicy)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	if input.AccountID == "" || input.SkillID == "" ||
		!validStatus(input.Status) || !validMemoryPolicy(input.MemoryPolicy) ||
		!validDigest(input.ConfigurationSchemaDigest) || input.ExpectedRevision < 0 ||
		input.IdempotencyKey == "" || len(input.IdempotencyKey) > 160 ||
		input.OccurredAt.IsZero() {
		return Command{}, ErrInvalidArgument
	}
	configuration, err := normalizeObject(input.ConfigurationData)
	if err != nil {
		return Command{}, err
	}
	connectors, err := normalizeRefs(input.ConnectorConnectionRefs)
	if err != nil {
		return Command{}, err
	}
	input.ConfigurationData = configuration
	input.ConnectorConnectionRefs = connectors
	input.OccurredAt = input.OccurredAt.UTC()
	payload, err := json.Marshal(struct {
		Operation                 string          `json:"operation"`
		AccountID                 string          `json:"accountId"`
		SkillID                   string          `json:"skillId"`
		Status                    string          `json:"status"`
		ConfigurationData         json.RawMessage `json:"configurationData"`
		ConfigurationSchemaDigest string          `json:"configurationSchemaDigest"`
		MemoryPolicy              string          `json:"memoryPolicy"`
		ConnectorConnectionRefs   []string        `json:"connectorConnectionRefs"`
		ExpectedRevision          int64           `json:"expectedRevision"`
	}{
		CommandPut,
		input.AccountID,
		input.SkillID,
		input.Status,
		input.ConfigurationData,
		input.ConfigurationSchemaDigest,
		input.MemoryPolicy,
		input.ConnectorConnectionRefs,
		input.ExpectedRevision,
	})
	if err != nil {
		return Command{}, ErrInvalidArgument
	}
	sum := sha256.Sum256(payload)
	return Command{
		PutInput:      input,
		RequestDigest: hex.EncodeToString(sum[:]),
	}, nil
}

func (setting Setting) Equivalent(command Command) bool {
	return setting.Status == command.Status &&
		setting.ConfigurationSchemaDigest == command.ConfigurationSchemaDigest &&
		setting.MemoryPolicy == command.MemoryPolicy &&
		string(setting.ConfigurationData) == string(command.ConfigurationData) &&
		strings.Join(setting.ConnectorConnectionRefs, "\x1f") ==
			strings.Join(command.ConnectorConnectionRefs, "\x1f")
}

func validStatus(value string) bool {
	return value == StatusEnabled || value == StatusDisabled
}

func validMemoryPolicy(value string) bool {
	return value == MemoryPackageDefault || value == MemoryConfirmBeforeSave || value == MemoryDisabled
}

func validDigest(value string) bool {
	if len(value) != len("sha256:")+sha256.Size*2 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	raw := strings.TrimPrefix(value, "sha256:")
	if raw != strings.ToLower(raw) {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}

func normalizeObject(raw json.RawMessage) (json.RawMessage, error) {
	if len(raw) == 0 || len(raw) > 64<<10 {
		return nil, ErrInvalidArgument
	}
	var value any
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, ErrInvalidArgument
	}
	if _, ok := value.(map[string]any); !ok {
		return nil, ErrInvalidArgument
	}
	canonical, err := json.Marshal(value)
	if err != nil {
		return nil, ErrInvalidArgument
	}
	return canonical, nil
}

func normalizeRefs(values []string) ([]string, error) {
	if values == nil || len(values) > 32 {
		return nil, ErrInvalidArgument
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || len(value) > 160 {
			return nil, ErrInvalidArgument
		}
		if _, duplicate := seen[value]; duplicate {
			return nil, ErrInvalidArgument
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result, nil
}
