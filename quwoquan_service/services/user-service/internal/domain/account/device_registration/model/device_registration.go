// Package model 定义 DeviceRegistration 聚合及其 owned DevicePushEndpoint。
// token 明文不属于领域状态；聚合只持有 AES-GCM 密文与 keyed fingerprint。
package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	maxAccountIDLength          = 96
	maxDeviceIDLength           = 128
	maxAppVersionLength         = 32
	maxInvalidationReasonLength = 256
	maxPushEndpoints            = 2
)

var (
	ErrInvalidRegistration = errors.New("device registration is invalid")
	ErrInvalidEndpoint     = errors.New("device push endpoint is invalid")
	ErrEndpointNotFound    = errors.New("device push endpoint not found")
	ErrInvalidTransition   = errors.New("device registration transition is invalid")
	ErrVersionConflict     = errors.New("device registration version conflict")
)

type Status string

const (
	StatusActive  Status = "active"
	StatusRevoked Status = "revoked"
	StatusStale   Status = "stale"
)

func (status Status) Valid() bool {
	switch status {
	case StatusActive, StatusRevoked, StatusStale:
		return true
	default:
		return false
	}
}

// State 是聚合持久化形态。PushEndpoints 始终按 endpointKind 排序以保证稳定快照。
type State struct {
	ID            string
	AccountID     string
	DeviceID      string
	AppVersion    string
	Status        Status
	Version       int64
	LastActiveAt  time.Time
	CreatedAt     time.Time
	UpdatedAt     time.Time
	PushEndpoints []EndpointState
}

// Snapshot 是 application 可返回的父聚合脱敏快照。
type Snapshot struct {
	ID           string
	AccountID    string
	DeviceID     string
	AppVersion   string
	Status       Status
	Version      int64
	LastActiveAt time.Time
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

type RegisterParams struct {
	AccountID    string
	DeviceID     string
	AppVersion   string
	RegisteredAt time.Time
}

// Mutation 同时携带父 version CAS 与本次实际变化 child 的 expected version。
// map value 为 0 表示首次插入，正数表示更新前 child version。
type Mutation struct {
	Aggregate                DeviceRegistration
	Changed                  bool
	EndpointRef              string
	ExpectedEndpointVersions map[string]int64
}

type DeviceRegistration struct {
	state State
}

func New(params RegisterParams) (DeviceRegistration, error) {
	params = normalizeRegisterParams(params)
	if err := validateRegisterParams(params); err != nil {
		return DeviceRegistration{}, err
	}
	state := State{
		ID:            canonicalRegistrationID(params.AccountID, params.DeviceID),
		AccountID:     params.AccountID,
		DeviceID:      params.DeviceID,
		AppVersion:    params.AppVersion,
		Status:        StatusActive,
		Version:       1,
		LastActiveAt:  params.RegisteredAt,
		CreatedAt:     params.RegisteredAt,
		UpdatedAt:     params.RegisteredAt,
		PushEndpoints: []EndpointState{},
	}
	return Restore(state)
}

func Restore(state State) (DeviceRegistration, error) {
	state = normalizeState(state)
	sortEndpoints(state.PushEndpoints)
	if err := validateState(state); err != nil {
		return DeviceRegistration{}, err
	}
	return DeviceRegistration{state: state}, nil
}

func (registration DeviceRegistration) State() State {
	return cloneState(registration.state)
}

func (registration DeviceRegistration) Snapshot() Snapshot {
	state := registration.state
	return Snapshot{
		ID:           state.ID,
		AccountID:    state.AccountID,
		DeviceID:     state.DeviceID,
		AppVersion:   state.AppVersion,
		Status:       state.Status,
		Version:      state.Version,
		LastActiveAt: state.LastActiveAt,
		CreatedAt:    state.CreatedAt,
		UpdatedAt:    state.UpdatedAt,
	}
}

func (registration DeviceRegistration) Validate() error {
	return validateState(registration.state)
}

// Register 仅供登录 coordinator 建立/刷新父设备登记，不处理 push token。
func (registration DeviceRegistration) Register(params RegisterParams) (Mutation, error) {
	if err := registration.Validate(); err != nil {
		return Mutation{}, err
	}
	params = normalizeRegisterParams(params)
	if err := validateRegisterParams(params); err != nil {
		return Mutation{}, err
	}
	if registration.state.AccountID != params.AccountID ||
		registration.state.DeviceID != params.DeviceID {
		return Mutation{}, fmt.Errorf("%w: registration identity cannot change", ErrInvalidRegistration)
	}
	if params.RegisteredAt.Before(registration.state.UpdatedAt) {
		return Mutation{}, fmt.Errorf("%w: registration clock cannot move backwards", ErrInvalidRegistration)
	}
	if registration.state.Status == StatusActive &&
		registration.state.AppVersion == params.AppVersion &&
		registration.state.LastActiveAt.Equal(params.RegisteredAt) {
		return Mutation{Aggregate: registration}, nil
	}
	next := registration.State()
	next.AppVersion = params.AppVersion
	next.Status = statusFromEndpoints(next.PushEndpoints, StatusActive)
	next.Version++
	next.LastActiveAt = params.RegisteredAt
	next.UpdatedAt = params.RegisteredAt
	updated, err := Restore(next)
	return Mutation{Aggregate: updated, Changed: err == nil}, err
}

func (registration DeviceRegistration) UpsertEndpoint(
	params UpsertEndpointParams,
) (Mutation, error) {
	if err := registration.Validate(); err != nil {
		return Mutation{}, err
	}
	params = normalizeUpsertEndpointParams(params)
	if err := validateUpsertEndpointParams(params); err != nil {
		return Mutation{}, err
	}
	if registration.state.AccountID != params.AccountID ||
		registration.state.DeviceID != params.DeviceID {
		return Mutation{}, fmt.Errorf("%w: endpoint owner identity cannot change", ErrInvalidEndpoint)
	}
	if params.UpdatedAt.Before(registration.state.UpdatedAt) {
		return Mutation{}, fmt.Errorf("%w: endpoint clock cannot move backwards", ErrInvalidEndpoint)
	}

	next := registration.State()
	index := endpointIndexByKind(next.PushEndpoints, params.Kind)
	if index >= 0 {
		current := next.PushEndpoints[index]
		if current.Status == StatusActive &&
			current.TokenFingerprint == params.TokenFingerprint &&
			next.AppVersion == params.AppVersion {
			return Mutation{
				Aggregate:   registration,
				EndpointRef: current.EndpointRef,
			}, nil
		}
		expected := current.Version
		current.TokenCiphertext = params.TokenCiphertext
		current.TokenFingerprint = params.TokenFingerprint
		current.Status = StatusActive
		current.InvalidationReason = ""
		current.Version++
		current.UpdatedAt = params.UpdatedAt
		next.PushEndpoints[index] = current
		next = advanceParent(next, params.AppVersion, params.UpdatedAt)
		updated, err := Restore(next)
		return Mutation{
			Aggregate:                updated,
			Changed:                  err == nil,
			EndpointRef:              current.EndpointRef,
			ExpectedEndpointVersions: map[string]int64{current.EndpointRef: expected},
		}, err
	}
	if len(next.PushEndpoints) >= maxPushEndpoints {
		return Mutation{}, fmt.Errorf("%w: endpoint cardinality exceeds two", ErrInvalidEndpoint)
	}
	endpoint := EndpointState{
		EndpointRef:      canonicalEndpointRef(params.AccountID, params.DeviceID, params.Kind),
		AccountID:        params.AccountID,
		DeviceID:         params.DeviceID,
		Kind:             params.Kind,
		TokenCiphertext:  params.TokenCiphertext,
		TokenFingerprint: params.TokenFingerprint,
		Status:           StatusActive,
		Version:          1,
		CreatedAt:        params.UpdatedAt,
		UpdatedAt:        params.UpdatedAt,
	}
	next.PushEndpoints = append(next.PushEndpoints, endpoint)
	next = advanceParent(next, params.AppVersion, params.UpdatedAt)
	updated, err := Restore(next)
	return Mutation{
		Aggregate:                updated,
		Changed:                  err == nil,
		EndpointRef:              endpoint.EndpointRef,
		ExpectedEndpointVersions: map[string]int64{endpoint.EndpointRef: 0},
	}, err
}

func (registration DeviceRegistration) RemoveEndpoint(
	kind EndpointKind,
	now time.Time,
) (Mutation, error) {
	if err := registration.Validate(); err != nil {
		return Mutation{}, err
	}
	kind = EndpointKind(strings.TrimSpace(string(kind)))
	now = now.UTC()
	if !kind.Valid() || now.IsZero() {
		return Mutation{}, fmt.Errorf("%w: remove input is invalid", ErrInvalidEndpoint)
	}
	next := registration.State()
	index := endpointIndexByKind(next.PushEndpoints, kind)
	if index < 0 {
		return Mutation{}, ErrEndpointNotFound
	}
	current := next.PushEndpoints[index]
	if current.Status == StatusRevoked {
		return Mutation{Aggregate: registration, EndpointRef: current.EndpointRef}, nil
	}
	if now.Before(registration.state.UpdatedAt) || now.Before(current.UpdatedAt) {
		return Mutation{}, fmt.Errorf("%w: removal clock cannot move backwards", ErrInvalidTransition)
	}
	expected := current.Version
	current.Status = StatusRevoked
	current.TokenCiphertext = ""
	current.TokenFingerprint = ""
	current.InvalidationReason = ""
	current.Version++
	current.UpdatedAt = now
	next.PushEndpoints[index] = current
	next = advanceParent(next, next.AppVersion, now)
	updated, err := Restore(next)
	return Mutation{
		Aggregate:                updated,
		Changed:                  err == nil,
		EndpointRef:              current.EndpointRef,
		ExpectedEndpointVersions: map[string]int64{current.EndpointRef: expected},
	}, err
}

func (registration DeviceRegistration) InvalidateEndpoint(
	endpointRef string,
	reason string,
	now time.Time,
) (Mutation, error) {
	if err := registration.Validate(); err != nil {
		return Mutation{}, err
	}
	endpointRef = strings.TrimSpace(endpointRef)
	reason = strings.TrimSpace(reason)
	now = now.UTC()
	if endpointRef == "" || invalidText(reason, maxInvalidationReasonLength) || now.IsZero() {
		return Mutation{}, fmt.Errorf("%w: invalidation input is invalid", ErrInvalidEndpoint)
	}
	next := registration.State()
	index := endpointIndexByRef(next.PushEndpoints, endpointRef)
	if index < 0 {
		return Mutation{}, ErrEndpointNotFound
	}
	current := next.PushEndpoints[index]
	if current.Status == StatusStale {
		return Mutation{Aggregate: registration, EndpointRef: current.EndpointRef}, nil
	}
	if current.Status != StatusActive {
		return Mutation{}, fmt.Errorf("%w: only active endpoint can become stale", ErrInvalidTransition)
	}
	if now.Before(registration.state.UpdatedAt) || now.Before(current.UpdatedAt) {
		return Mutation{}, fmt.Errorf("%w: invalidation clock cannot move backwards", ErrInvalidTransition)
	}
	expected := current.Version
	current.Status = StatusStale
	current.TokenCiphertext = ""
	current.TokenFingerprint = ""
	current.InvalidationReason = reason
	current.Version++
	current.UpdatedAt = now
	next.PushEndpoints[index] = current
	next = advanceParent(next, next.AppVersion, now)
	updated, err := Restore(next)
	return Mutation{
		Aggregate:                updated,
		Changed:                  err == nil,
		EndpointRef:              current.EndpointRef,
		ExpectedEndpointVersions: map[string]int64{current.EndpointRef: expected},
	}, err
}

func (registration DeviceRegistration) EndpointByRef(
	endpointRef string,
) (EndpointState, bool) {
	index := endpointIndexByRef(registration.state.PushEndpoints, strings.TrimSpace(endpointRef))
	if index < 0 {
		return EndpointState{}, false
	}
	return registration.state.PushEndpoints[index], true
}

func (registration DeviceRegistration) EndpointByKind(
	kind EndpointKind,
) (EndpointState, bool) {
	index := endpointIndexByKind(registration.state.PushEndpoints, kind)
	if index < 0 {
		return EndpointState{}, false
	}
	return registration.state.PushEndpoints[index], true
}

func advanceParent(state State, appVersion string, now time.Time) State {
	state.AppVersion = appVersion
	state.Status = statusFromEndpoints(state.PushEndpoints, StatusActive)
	state.Version++
	state.LastActiveAt = now
	state.UpdatedAt = now
	sortEndpoints(state.PushEndpoints)
	return state
}

func statusFromEndpoints(endpoints []EndpointState, emptyFallback Status) Status {
	if len(endpoints) == 0 {
		return emptyFallback
	}
	hasStale := false
	for _, endpoint := range endpoints {
		if endpoint.Status == StatusActive {
			return StatusActive
		}
		if endpoint.Status == StatusStale {
			hasStale = true
		}
	}
	if hasStale {
		return StatusStale
	}
	return StatusRevoked
}

func normalizeRegisterParams(params RegisterParams) RegisterParams {
	params.AccountID = strings.TrimSpace(params.AccountID)
	params.DeviceID = strings.TrimSpace(params.DeviceID)
	params.AppVersion = strings.TrimSpace(params.AppVersion)
	params.RegisteredAt = params.RegisteredAt.UTC()
	return params
}

func validateRegisterParams(params RegisterParams) error {
	if invalidText(params.AccountID, maxAccountIDLength) ||
		invalidText(params.DeviceID, maxDeviceIDLength) ||
		invalidOptionalText(params.AppVersion, maxAppVersionLength) ||
		params.RegisteredAt.IsZero() {
		return fmt.Errorf("%w: registration input is incomplete or malformed", ErrInvalidRegistration)
	}
	return nil
}

func normalizeState(state State) State {
	state.ID = strings.TrimSpace(state.ID)
	state.AccountID = strings.TrimSpace(state.AccountID)
	state.DeviceID = strings.TrimSpace(state.DeviceID)
	state.AppVersion = strings.TrimSpace(state.AppVersion)
	state.LastActiveAt = state.LastActiveAt.UTC()
	state.CreatedAt = state.CreatedAt.UTC()
	state.UpdatedAt = state.UpdatedAt.UTC()
	state.PushEndpoints = append([]EndpointState(nil), state.PushEndpoints...)
	for index := range state.PushEndpoints {
		endpoint := &state.PushEndpoints[index]
		endpoint.EndpointRef = strings.TrimSpace(endpoint.EndpointRef)
		endpoint.AccountID = strings.TrimSpace(endpoint.AccountID)
		endpoint.DeviceID = strings.TrimSpace(endpoint.DeviceID)
		endpoint.Kind = EndpointKind(strings.TrimSpace(string(endpoint.Kind)))
		endpoint.TokenCiphertext = strings.TrimSpace(endpoint.TokenCiphertext)
		endpoint.TokenFingerprint = strings.TrimSpace(endpoint.TokenFingerprint)
		endpoint.InvalidationReason = strings.TrimSpace(endpoint.InvalidationReason)
		endpoint.CreatedAt = endpoint.CreatedAt.UTC()
		endpoint.UpdatedAt = endpoint.UpdatedAt.UTC()
	}
	return state
}

func validateState(state State) error {
	if state.ID != canonicalRegistrationID(state.AccountID, state.DeviceID) ||
		invalidText(state.AccountID, maxAccountIDLength) ||
		invalidText(state.DeviceID, maxDeviceIDLength) ||
		invalidOptionalText(state.AppVersion, maxAppVersionLength) ||
		!state.Status.Valid() ||
		state.Version < 1 ||
		state.LastActiveAt.IsZero() ||
		state.CreatedAt.IsZero() ||
		state.UpdatedAt.IsZero() ||
		state.LastActiveAt.Before(state.CreatedAt) ||
		state.LastActiveAt.After(state.UpdatedAt) ||
		state.UpdatedAt.Before(state.CreatedAt) ||
		len(state.PushEndpoints) > maxPushEndpoints {
		return fmt.Errorf("%w: persisted registration state is malformed", ErrInvalidRegistration)
	}
	seenKinds := map[EndpointKind]struct{}{}
	seenRefs := map[string]struct{}{}
	for _, endpoint := range state.PushEndpoints {
		if err := validateEndpointState(endpoint, state.AccountID, state.DeviceID); err != nil {
			return err
		}
		if _, exists := seenKinds[endpoint.Kind]; exists {
			return fmt.Errorf("%w: duplicate endpoint kind", ErrInvalidRegistration)
		}
		if _, exists := seenRefs[endpoint.EndpointRef]; exists {
			return fmt.Errorf("%w: duplicate endpoint ref", ErrInvalidRegistration)
		}
		seenKinds[endpoint.Kind] = struct{}{}
		seenRefs[endpoint.EndpointRef] = struct{}{}
	}
	if len(state.PushEndpoints) > 0 &&
		state.Status != statusFromEndpoints(state.PushEndpoints, state.Status) {
		return fmt.Errorf("%w: parent and child lifecycle diverged", ErrInvalidRegistration)
	}
	return nil
}

func canonicalRegistrationID(accountID, deviceID string) string {
	return canonicalDigest(accountID, deviceID)
}

func cloneState(state State) State {
	state.PushEndpoints = append([]EndpointState(nil), state.PushEndpoints...)
	return state
}

func invalidText(value string, maxLength int) bool {
	return value == "" ||
		strings.TrimSpace(value) != value ||
		len(value) > maxLength
}

func invalidOptionalText(value string, maxLength int) bool {
	return value != "" &&
		(strings.TrimSpace(value) != value || len(value) > maxLength)
}
