// Package persistence 实现 DeviceRegistration 对象专属 PostgreSQL Store/readers。
package persistence

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	registrationports "quwoquan_service/services/user-service/internal/account/device_registration/domain/ports"
)

const (
	activeTokenFingerprintConstraint = "uq_device_push_endpoints_active_token_fingerprint"
	endpointIdentityConstraint       = "uq_device_push_endpoints_identity"
	registrationIdentityConstraint   = "uq_user_devices_account_device"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("DeviceRegistration PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

var (
	_ registrationports.AggregateStore                            = (*PostgresStore)(nil)
	_ registrationports.ResolveIncomingCallPushDestinationsReader = (*PostgresStore)(nil)
	_ registrationports.ResolvePushEndpointSecretReader           = (*PostgresStore)(nil)
)

func (store *PostgresStore) Load(
	ctx context.Context,
	accountID string,
	deviceID string,
) (registrationmodel.DeviceRegistration, bool, error) {
	accountID = strings.TrimSpace(accountID)
	deviceID = strings.TrimSpace(deviceID)
	if accountID == "" || deviceID == "" {
		return registrationmodel.DeviceRegistration{}, false,
			registrationmodel.ErrInvalidRegistration
	}
	state, found, err := scanRegistrationState(store.pool.QueryRow(ctx, `
SELECT
  id, account_id, device_id, COALESCE(app_version, ''),
  status, version, last_active_at, created_at, updated_at
FROM user_devices
WHERE account_id=$1 AND device_id=$2`,
		accountID,
		deviceID,
	))
	if err != nil || !found {
		return registrationmodel.DeviceRegistration{}, found, err
	}
	endpoints, err := store.loadEndpoints(ctx, accountID, deviceID)
	if err != nil {
		return registrationmodel.DeviceRegistration{}, false, err
	}
	state.PushEndpoints = endpoints
	registration, err := registrationmodel.Restore(state)
	if err != nil {
		return registrationmodel.DeviceRegistration{}, false,
			fmt.Errorf("restore device registration: %w", err)
	}
	return registration, true, nil
}

func (store *PostgresStore) LoadByEndpointRef(
	ctx context.Context,
	endpointRef string,
) (registrationmodel.DeviceRegistration, bool, error) {
	endpointRef = strings.TrimSpace(endpointRef)
	if endpointRef == "" {
		return registrationmodel.DeviceRegistration{}, false,
			registrationmodel.ErrEndpointNotFound
	}
	var accountID, deviceID string
	err := store.pool.QueryRow(ctx, `
SELECT account_id, device_id
FROM device_push_endpoints
WHERE endpoint_ref=$1`,
		endpointRef,
	).Scan(&accountID, &deviceID)
	if errors.Is(err, pgx.ErrNoRows) {
		return registrationmodel.DeviceRegistration{}, false, nil
	}
	if err != nil {
		return registrationmodel.DeviceRegistration{}, false,
			fmt.Errorf("locate device push endpoint owner: %w", err)
	}
	return store.Load(ctx, accountID, deviceID)
}

func (store *PostgresStore) Commit(
	ctx context.Context,
	mutation registrationports.CommitMutation,
) error {
	if err := mutation.Registration.Validate(); err != nil {
		return err
	}
	state := mutation.Registration.State()
	if mutation.ExpectedAggregateVersion < 0 {
		return registrationmodel.ErrVersionConflict
	}
	if mutation.ExpectedAggregateVersion > 0 &&
		state.Version != mutation.ExpectedAggregateVersion+1 {
		return registrationmodel.ErrVersionConflict
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if err != nil {
		return fmt.Errorf("begin device registration transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if err := commitRegistrationRow(
		ctx,
		tx,
		mutation.ExpectedAggregateVersion,
		state,
	); err != nil {
		return err
	}
	refs := make([]string, 0, len(mutation.ExpectedEndpointVersions))
	for endpointRef := range mutation.ExpectedEndpointVersions {
		refs = append(refs, endpointRef)
	}
	sort.Strings(refs)
	for _, endpointRef := range refs {
		endpoint, found := endpointByRef(state.PushEndpoints, endpointRef)
		if !found {
			return registrationmodel.ErrVersionConflict
		}
		if err := commitEndpointRow(
			ctx,
			tx,
			mutation.ExpectedEndpointVersions[endpointRef],
			endpoint,
		); err != nil {
			return err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return mapWriteError(err)
	}
	return nil
}

func (store *PostgresStore) ListActivePushDestinations(
	ctx context.Context,
	accountID string,
) ([]registrationports.PushDestinationRef, error) {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return nil, registrationmodel.ErrInvalidRegistration
	}
	rows, err := store.pool.Query(ctx, `
SELECT endpoint_ref, device_id, endpoint_kind
FROM device_push_endpoints
WHERE account_id=$1 AND status='active'
ORDER BY device_id, endpoint_kind`,
		accountID,
	)
	if err != nil {
		return nil, fmt.Errorf("list active device push destinations: %w", err)
	}
	defer rows.Close()
	result := make([]registrationports.PushDestinationRef, 0)
	for rows.Next() {
		var ref registrationports.PushDestinationRef
		var kind string
		if err := rows.Scan(&ref.EndpointRef, &ref.DeviceID, &kind); err != nil {
			return nil, fmt.Errorf("scan active device push destination: %w", err)
		}
		ref.Kind = registrationmodel.EndpointKind(kind)
		if !ref.Kind.Valid() {
			return nil, registrationmodel.ErrInvalidEndpoint
		}
		result = append(result, ref)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate active device push destinations: %w", err)
	}
	return result, nil
}

func (store *PostgresStore) FindPushEndpointByRef(
	ctx context.Context,
	endpointRef string,
) (registrationmodel.EndpointState, bool, error) {
	endpointRef = strings.TrimSpace(endpointRef)
	if endpointRef == "" {
		return registrationmodel.EndpointState{}, false,
			registrationmodel.ErrEndpointNotFound
	}
	return scanEndpoint(store.pool.QueryRow(ctx, `
SELECT
  endpoint_ref, account_id, device_id, endpoint_kind,
  COALESCE(token_ciphertext, ''), COALESCE(token_fingerprint, ''),
  status, COALESCE(invalidation_reason, ''), version, created_at, updated_at
FROM device_push_endpoints
WHERE endpoint_ref=$1`,
		endpointRef,
	))
}

func (store *PostgresStore) loadEndpoints(
	ctx context.Context,
	accountID string,
	deviceID string,
) ([]registrationmodel.EndpointState, error) {
	rows, err := store.pool.Query(ctx, `
SELECT
  endpoint_ref, account_id, device_id, endpoint_kind,
  COALESCE(token_ciphertext, ''), COALESCE(token_fingerprint, ''),
  status, COALESCE(invalidation_reason, ''), version, created_at, updated_at
FROM device_push_endpoints
WHERE account_id=$1 AND device_id=$2
ORDER BY endpoint_kind`,
		accountID,
		deviceID,
	)
	if err != nil {
		return nil, fmt.Errorf("load device push endpoints: %w", err)
	}
	defer rows.Close()
	endpoints := make([]registrationmodel.EndpointState, 0, 2)
	for rows.Next() {
		endpoint, _, err := scanEndpoint(rows)
		if err != nil {
			return nil, err
		}
		endpoints = append(endpoints, endpoint)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate device push endpoints: %w", err)
	}
	return endpoints, nil
}

func commitRegistrationRow(
	ctx context.Context,
	tx pgx.Tx,
	expectedVersion int64,
	state registrationmodel.State,
) error {
	var (
		tag pgconn.CommandTag
		err error
	)
	if expectedVersion == 0 {
		tag, err = tx.Exec(ctx, `
INSERT INTO user_devices (
  id, account_id, device_id, app_version,
  status, version, last_active_at, created_at, updated_at
) VALUES (
  $1,$2,$3,NULLIF($4,''),$5,$6,$7,$8,$9
)`,
			state.ID,
			state.AccountID,
			state.DeviceID,
			state.AppVersion,
			state.Status,
			state.Version,
			state.LastActiveAt,
			state.CreatedAt,
			state.UpdatedAt,
		)
	} else {
		tag, err = tx.Exec(ctx, `
UPDATE user_devices SET
  app_version=NULLIF($3,''),
  status=$4,
  version=$5,
  last_active_at=$6,
  updated_at=$7
WHERE account_id=$1 AND device_id=$2 AND version=$8`,
			state.AccountID,
			state.DeviceID,
			state.AppVersion,
			state.Status,
			state.Version,
			state.LastActiveAt,
			state.UpdatedAt,
			expectedVersion,
		)
	}
	if err != nil {
		return mapWriteError(err)
	}
	if tag.RowsAffected() != 1 {
		return registrationmodel.ErrVersionConflict
	}
	return nil
}

func commitEndpointRow(
	ctx context.Context,
	tx pgx.Tx,
	expectedVersion int64,
	endpoint registrationmodel.EndpointState,
) error {
	var (
		tag pgconn.CommandTag
		err error
	)
	if expectedVersion == 0 {
		if endpoint.Version != 1 {
			return registrationmodel.ErrVersionConflict
		}
		tag, err = tx.Exec(ctx, `
INSERT INTO device_push_endpoints (
  endpoint_ref, account_id, device_id, endpoint_kind,
  token_ciphertext, token_fingerprint, status, invalidation_reason,
  version, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,NULLIF($5,''),NULLIF($6,''),$7,NULLIF($8,''),
  $9,$10,$11
)`,
			endpoint.EndpointRef,
			endpoint.AccountID,
			endpoint.DeviceID,
			endpoint.Kind,
			endpoint.TokenCiphertext,
			endpoint.TokenFingerprint,
			endpoint.Status,
			endpoint.InvalidationReason,
			endpoint.Version,
			endpoint.CreatedAt,
			endpoint.UpdatedAt,
		)
	} else {
		if endpoint.Version != expectedVersion+1 {
			return registrationmodel.ErrVersionConflict
		}
		tag, err = tx.Exec(ctx, `
UPDATE device_push_endpoints SET
  token_ciphertext=NULLIF($2,''),
  token_fingerprint=NULLIF($3,''),
  status=$4,
  invalidation_reason=NULLIF($5,''),
  version=$6,
  updated_at=$7
WHERE endpoint_ref=$1 AND version=$8`,
			endpoint.EndpointRef,
			endpoint.TokenCiphertext,
			endpoint.TokenFingerprint,
			endpoint.Status,
			endpoint.InvalidationReason,
			endpoint.Version,
			endpoint.UpdatedAt,
			expectedVersion,
		)
	}
	if err != nil {
		return mapWriteError(err)
	}
	if tag.RowsAffected() != 1 {
		return registrationmodel.ErrVersionConflict
	}
	return nil
}

func mapWriteError(err error) error {
	var postgresError *pgconn.PgError
	if !errors.As(err, &postgresError) {
		if errors.Is(err, pgx.ErrTxCommitRollback) {
			return registrationmodel.ErrVersionConflict
		}
		return fmt.Errorf("persist device registration: %w", err)
	}
	if postgresError.Code == "40001" {
		return registrationmodel.ErrVersionConflict
	}
	if postgresError.Code != "23505" {
		return fmt.Errorf("persist device registration: %w", err)
	}
	switch postgresError.ConstraintName {
	case activeTokenFingerprintConstraint:
		return registrationports.ErrActiveTokenConflict
	case endpointIdentityConstraint, registrationIdentityConstraint,
		"device_push_endpoints_pkey", "user_devices_pkey":
		return registrationmodel.ErrVersionConflict
	default:
		return fmt.Errorf("persist device registration unique constraint: %w", err)
	}
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanRegistrationState(
	row rowScanner,
) (registrationmodel.State, bool, error) {
	var state registrationmodel.State
	var status string
	err := row.Scan(
		&state.ID,
		&state.AccountID,
		&state.DeviceID,
		&state.AppVersion,
		&status,
		&state.Version,
		&state.LastActiveAt,
		&state.CreatedAt,
		&state.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return registrationmodel.State{}, false, nil
	}
	if err != nil {
		return registrationmodel.State{}, false,
			fmt.Errorf("scan device registration: %w", err)
	}
	state.Status = registrationmodel.Status(status)
	return state, true, nil
}

func scanEndpoint(
	row rowScanner,
) (registrationmodel.EndpointState, bool, error) {
	var endpoint registrationmodel.EndpointState
	var kind, status string
	err := row.Scan(
		&endpoint.EndpointRef,
		&endpoint.AccountID,
		&endpoint.DeviceID,
		&kind,
		&endpoint.TokenCiphertext,
		&endpoint.TokenFingerprint,
		&status,
		&endpoint.InvalidationReason,
		&endpoint.Version,
		&endpoint.CreatedAt,
		&endpoint.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return registrationmodel.EndpointState{}, false, nil
	}
	if err != nil {
		return registrationmodel.EndpointState{}, false,
			fmt.Errorf("scan device push endpoint: %w", err)
	}
	endpoint.Kind = registrationmodel.EndpointKind(kind)
	endpoint.Status = registrationmodel.Status(status)
	return endpoint, true, nil
}

func endpointByRef(
	endpoints []registrationmodel.EndpointState,
	endpointRef string,
) (registrationmodel.EndpointState, bool) {
	for _, endpoint := range endpoints {
		if endpoint.EndpointRef == endpointRef {
			return endpoint, true
		}
	}
	return registrationmodel.EndpointState{}, false
}
