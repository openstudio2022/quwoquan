package persistence

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

// PgPersonaRelationshipStore is the single authoritative store for every
// direction in a persona pair. It deliberately owns follow and block together
// so a block can clear both follow directions and write the outbox atomically.
type PgPersonaRelationshipStore struct {
	pool         *pgxpool.Pool
	now          func() time.Time
	cursorSigner *relationshipapp.ReadCursorSigner
}

var _ relports.PersonaRelationshipStore = (*PgPersonaRelationshipStore)(nil)
var _ relports.PersonaRelationshipOutbox = (*PgPersonaRelationshipStore)(nil)

func NewPgPersonaRelationshipStore(pool *pgxpool.Pool) *PgPersonaRelationshipStore {
	// 游标只携带读坐标，不承载授权，但仍必须防篡改和跨查询复用。每个服务
	// 进程生成独立不可预测材料；滚动重启会明确拒绝旧游标，而不会误解码为首屏。
	material := make([]byte, 32)
	if _, err := rand.Read(material); err != nil {
		panic("generate relationship read cursor key: " + err.Error())
	}
	signer, err := relationshipapp.NewReadCursorSigner(material)
	if err != nil {
		panic("initialize relationship read cursor signer: " + err.Error())
	}
	return &PgPersonaRelationshipStore{pool: pool, now: func() time.Time { return time.Now().UTC() }, cursorSigner: signer}
}

func (s *PgPersonaRelationshipStore) WithReadCursorSigner(signer *relationshipapp.ReadCursorSigner) *PgPersonaRelationshipStore {
	s.SetReadCursorSigner(signer)
	return s
}

func (s *PgPersonaRelationshipStore) SetReadCursorSigner(signer *relationshipapp.ReadCursorSigner) {
	if s != nil && signer != nil {
		s.cursorSigner = signer
	}
}

// WithClock installs one clock for acceptance/finalization arbitration tests.
// Production retains the UTC system clock.
func (s *PgPersonaRelationshipStore) WithClock(now func() time.Time) *PgPersonaRelationshipStore {
	if s != nil && now != nil {
		s.now = now
	}
	return s
}

func (s *PgPersonaRelationshipStore) Apply(
	ctx context.Context,
	command relmodel.Command,
) (relmodel.MutationResult, error) {
	pair, err := relmodel.NewPair(command.SourcePersonaID, command.TargetPersonaID)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if s == nil || s.pool == nil {
		return relmodel.MutationResult{}, errors.New("persona relationship store is unavailable")
	}

	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("begin persona relationship transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	if command.IdempotencyKey == "" {
		return relmodel.MutationResult{}, relmodel.ErrIdempotencyKeyRequired
	}
	// 固定锁序：生效政策共享锁 → 幂等锁 → Pair 锁 → source quota 锁。
	// 共享锁不串行每个关注，也不产生每次递增的全局 policy 热点。
	policy, err := loadActivatedFollowPolicy(ctx, tx)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if err := lockIdempotencyKey(ctx, tx, command.SourcePersonaID, command.IdempotencyKey); err != nil {
		return relmodel.MutationResult{}, err
	}
	replay, found, err := loadReceipt(ctx, tx, command)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if found {
		if replay.Outcome == relmodel.OutcomeExpired {
			// 到期终结已在同一 receipt 身份上赢得仲裁；该命令不能再被执行。
			return relmodel.MutationResult{}, relmodel.ErrCommandAlreadyFinalized
		}
		if err := tx.Commit(ctx); err != nil {
			return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship replay: %w", err)
		}
		committed = true
		replay.IdempotentReplay = true
		return replay, nil
	}

	if command.AcceptUntil.IsZero() || !s.now().UTC().Before(command.AcceptUntil) {
		return relmodel.MutationResult{}, relmodel.ErrCommandAlreadyFinalized
	}
	version, exists, err := lockPair(ctx, tx, pair, command.Kind)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if !exists {
		return relmodel.MutationResult{}, errors.New("persona relationship pair was not materialized")
	}
	if command.ExpectedVersion != nil && *command.ExpectedVersion != version {
		// 旧版本的离线请求不得越过较新的决定，包括较新的「保持不变」。
		return relmodel.MutationResult{}, fmt.Errorf(
			"%w: expected %d, current %d",
			relmodel.ErrVersionConflict, *command.ExpectedVersion, version,
		)
	}

	directions, err := loadLockedDirections(ctx, tx, pair.ID)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	result, dirty, err := applyCommand(command, pair, version, directions)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	// 名额只在真实新增/释放主动关注时变动，并与关系边在同一事务提交。
	// 超额是确定拒绝：不写成功事实、不留 pending、不后台重试。
	quotaDeltas := followingQuotaDeltas(command, result)
	quotaSources := make([]string, 0, len(quotaDeltas))
	for source := range quotaDeltas {
		quotaSources = append(quotaSources, source)
	}
	sort.Strings(quotaSources)
	for _, source := range quotaSources {
		if err := applyFollowQuotaDelta(ctx, tx, source, quotaDeltas[source], policy); err != nil {
			return relmodel.MutationResult{}, err
		}
	}
	// 每个新接纳的命令都推进一次聚合版本，包括无变化决定。版本是写栅栏：
	// 若 no-op 不推进，旧离线请求就能覆盖较新的「保持不变」。
	version++
	result.State.Version = version
	result.Outcome = relmodel.OutcomeCommitted
	if _, err := tx.Exec(ctx, `
			UPDATE persona_relationships
			SET version = $2, updated_at = $3
			WHERE pair_id = $1`, pair.ID, version, result.OccurredAt); err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("advance persona relationship version: %w", err)
	}
	if result.Changed {
		for _, direction := range dirty {
			if err := upsertDirection(ctx, tx, direction); err != nil {
				return relmodel.MutationResult{}, err
			}
		}
		// 只有真实业务变化才追加 outbox；no-op 不产生业务事件、计数或贡献。
		if err := appendOutbox(ctx, tx, pair.ID, version, command, result); err != nil {
			return relmodel.MutationResult{}, err
		}
	}
	if err := saveReceipt(ctx, tx, command, pair.ID, result.State.Version, result); err != nil {
		return relmodel.MutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship command: %w", err)
	}
	committed = true
	return result, nil
}

// Recover reads one historical receipt without deriving history from the current
// relationship boolean. Missing receipt is reported separately so the caller can
// return history_unavailable.
func (s *PgPersonaRelationshipStore) Recover(ctx context.Context, actorPersonaID, idempotencyKey string, operation relmodel.CommandKind, targetPersonaID string) (relmodel.MutationResult, bool, error) {
	if s == nil || s.pool == nil {
		return relmodel.MutationResult{}, false, errors.New("persona relationship store is unavailable")
	}
	var storedOperation, storedTarget, outcome string
	var payload []byte
	err := s.pool.QueryRow(ctx, `SELECT operation,target_persona_id,outcome,response_json FROM persona_relationship_command_receipts WHERE actor_persona_id=$1 AND idempotency_key=$2`, strings.TrimSpace(actorPersonaID), strings.TrimSpace(idempotencyKey)).Scan(&storedOperation, &storedTarget, &outcome, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return relmodel.MutationResult{}, false, nil
	}
	if err != nil {
		return relmodel.MutationResult{}, false, fmt.Errorf("read persona relationship receipt: %w", err)
	}
	if storedOperation != string(operation) || storedTarget != strings.TrimSpace(targetPersonaID) {
		return relmodel.MutationResult{}, false, relmodel.ErrIdempotencyConflict
	}
	result, err := decodePersonaRelationshipReceipt(payload)
	if err != nil {
		return relmodel.MutationResult{}, false, err
	}
	result.Outcome = relmodel.CommandOutcome(outcome)
	return result, true, nil
}

// FinalizeExpired 在同一条 receipt 身份上把未决命令终结为「确定未执行」。
// 它与原写竞争同一唯一键：恰有一个赢家。原写已提交时返回既有 committed 结果，
// 终结成功时返回 expired，调用方据此撤去 unknown 而不是伪造成功。
func (s *PgPersonaRelationshipStore) FinalizeExpired(
	ctx context.Context,
	actorPersonaID string,
	idempotencyKey string,
	operation relmodel.CommandKind,
	targetPersonaID string,
	acceptUntil time.Time,
) (relmodel.MutationResult, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if actorPersonaID == "" || idempotencyKey == "" {
		return relmodel.MutationResult{}, relmodel.ErrIdempotencyKeyRequired
	}
	if acceptUntil.IsZero() || s.now().UTC().Before(acceptUntil) {
		return relmodel.MutationResult{}, relmodel.ErrCommandAlreadyFinalized
	}
	if s == nil || s.pool == nil {
		return relmodel.MutationResult{}, errors.New("persona relationship store is unavailable")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("begin persona relationship finalize: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	if err := lockIdempotencyKey(ctx, tx, actorPersonaID, idempotencyKey); err != nil {
		return relmodel.MutationResult{}, err
	}
	command := relmodel.Command{
		Kind:            operation,
		SourcePersonaID: actorPersonaID,
		TargetPersonaID: strings.TrimSpace(targetPersonaID),
		IdempotencyKey:  idempotencyKey,
		AcceptUntil:     acceptUntil,
	}
	existing, found, err := loadReceipt(ctx, tx, command)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if found {
		if err := tx.Commit(ctx); err != nil {
			return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship finalize replay: %w", err)
		}
		committed = true
		existing.IdempotentReplay = true
		return existing, nil
	}
	now := s.now().UTC()
	result := relmodel.MutationResult{OccurredAt: now, Outcome: relmodel.OutcomeExpired}
	if err := saveReceipt(ctx, tx, command, "", 0, result); err != nil {
		return relmodel.MutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship finalize: %w", err)
	}
	committed = true
	return result, nil
}

// activatedFollowPolicy 是生效配置的只读提交快照。
// 它是现役配置发布的执行物化：命令只用该快照，不信任各副本未追齐的内存值。
type activatedFollowPolicy struct {
	Revision               int64
	MaxFollowingPerPersona int
}

const followPolicyID = "persona_following"

// loadActivatedFollowPolicy 以共享锁读取生效政策。
// 共享锁允许并发关注并行执行，同时让配置激活的排他锁能等待在飞行的旧写结束。
func loadActivatedFollowPolicy(ctx context.Context, tx pgx.Tx) (activatedFollowPolicy, error) {
	var policy activatedFollowPolicy
	err := tx.QueryRow(ctx, `
		SELECT revision, max_following_per_persona
		FROM relationship_policy_activation
		WHERE policy_id = $1
		FOR SHARE`, followPolicyID,
	).Scan(&policy.Revision, &policy.MaxFollowingPerPersona)
	if errors.Is(err, pgx.ErrNoRows) {
		return activatedFollowPolicy{}, relmodel.ErrFollowPolicyUnavailable
	}
	if err != nil {
		return activatedFollowPolicy{}, fmt.Errorf("read activated follow policy: %w", err)
	}
	if policy.MaxFollowingPerPersona < 1 {
		return activatedFollowPolicy{}, relmodel.ErrFollowPolicyUnavailable
	}
	return policy, nil
}

// followingQuotaDelta 返回本次命令对 source 主动关注名额的精确变化量。
// 只有真实生效的 follow 增加占用；unfollow 与双向 block 清边释放占用。
func followingQuotaDeltas(command relmodel.Command, result relmodel.MutationResult) map[string]int {
	deltas := map[string]int{}
	if !result.Changed {
		return deltas
	}
	switch command.Kind {
	case relmodel.CommandFollow:
		deltas[command.SourcePersonaID] = 1
	case relmodel.CommandUnfollow:
		deltas[command.SourcePersonaID] = -1
	case relmodel.CommandBlock:
		for _, direction := range result.ClearedFollowing {
			deltas[direction.SourcePersonaID]--
		}
	}
	return deltas
}

// applyFollowQuotaDelta 在 source quota 行锁内条件占用或释放名额。
// 名额是精确事实：不依赖异步公开数字，也不在每次关注里 COUNT 全部出边。
func applyFollowQuotaDelta(
	ctx context.Context,
	tx pgx.Tx,
	sourcePersonaID string,
	delta int,
	policy activatedFollowPolicy,
) error {
	sourcePersonaID = strings.TrimSpace(sourcePersonaID)
	if sourcePersonaID == "" {
		return relmodel.ErrInvalidPersonaPair
	}
	var current int
	err := tx.QueryRow(ctx, `
		INSERT INTO persona_follow_quota (source_persona_id, following_count, policy_revision)
		VALUES ($1, 0, $2)
		ON CONFLICT (source_persona_id) DO UPDATE
		SET source_persona_id = persona_follow_quota.source_persona_id
		RETURNING following_count`, sourcePersonaID, policy.Revision,
	).Scan(&current)
	if err != nil {
		return fmt.Errorf("lock persona follow quota: %w", err)
	}
	next := current + delta
	if next < 0 {
		next = 0
	}
	// 下调限额保留既有关系，只拒绝新增：因此仅在净增长时校验上限。
	if delta > 0 && next > policy.MaxFollowingPerPersona {
		return fmt.Errorf(
			"%w: persona holds %d of %d following slots",
			relmodel.ErrFollowingLimitExceeded, current, policy.MaxFollowingPerPersona,
		)
	}
	if _, err := tx.Exec(ctx, `
		UPDATE persona_follow_quota
		SET following_count = $2, policy_revision = $3, updated_at = NOW()
		WHERE source_persona_id = $1`,
		sourcePersonaID, next, policy.Revision,
	); err != nil {
		return fmt.Errorf("apply persona follow quota delta: %w", err)
	}
	return nil
}

func lockIdempotencyKey(ctx context.Context, tx pgx.Tx, actorPersonaID, key string) error {
	// PostgreSQL text parameters cannot contain NUL. Hash the structured input
	// before it reaches SQL so delimiters in IDs or client keys cannot alias a
	// different command and no binary control character reaches the driver.
	digest := sha256.Sum256([]byte(actorPersonaID + "\x1f" + key))
	lockKey := hex.EncodeToString(digest[:])
	_, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, lockKey)
	if err != nil {
		return fmt.Errorf("lock persona relationship idempotency key: %w", err)
	}
	return nil
}

func loadReceipt(ctx context.Context, tx pgx.Tx, command relmodel.Command) (relmodel.MutationResult, bool, error) {
	var (
		operation           string
		target              string
		outcome             string
		storedCommandDigest string
		storedBasisDigest   string
		payload             []byte
	)
	err := tx.QueryRow(ctx, `
		SELECT operation, target_persona_id, outcome, command_digest, basis_digest, response_json
		FROM persona_relationship_command_receipts
		WHERE actor_persona_id = $1 AND idempotency_key = $2
		FOR UPDATE`,
		command.SourcePersonaID, command.IdempotencyKey,
	).Scan(&operation, &target, &outcome, &storedCommandDigest, &storedBasisDigest, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return relmodel.MutationResult{}, false, nil
	}
	if err != nil {
		return relmodel.MutationResult{}, false, fmt.Errorf("load persona relationship receipt: %w", err)
	}
	if operation != string(command.Kind) || target != command.TargetPersonaID {
		return relmodel.MutationResult{}, false, relmodel.ErrIdempotencyConflict
	}
	if strings.TrimSpace(command.MutationBasis) != "" &&
		(storedCommandDigest != relationshipCommandDigest(command) || storedBasisDigest != relationshipBasisDigest(command.MutationBasis)) {
		return relmodel.MutationResult{}, false, relmodel.ErrIdempotencyConflict
	}
	result, err := decodePersonaRelationshipReceipt(payload)
	if err != nil {
		return relmodel.MutationResult{}, false, fmt.Errorf("decode persona relationship receipt: %w", err)
	}
	result.Outcome = relmodel.CommandOutcome(outcome)
	return result, true, nil
}

// personaRelationshipReceiptDTO 是 receipt 存储边界的唯一 JSON 合同。
// RelationshipState 在 API 面上刻意不可序列化（json:"-"），直接 Marshal
// 领域 MutationResult 会把 state 存成空对象，回放时 Version/IsFollowing
// 等字段全部漂移为零值；显式 DTO 保证回放响应与原响应逐字段一致。
type personaRelationshipReceiptDTO struct {
	State            personaRelationshipReceiptStateDTO       `json:"state"`
	ClearedFollowing []personaRelationshipReceiptDirectionDTO `json:"clearedFollowing,omitempty"`
	Changed          bool                                     `json:"changed"`
	EventName        string                                   `json:"eventName,omitempty"`
	OccurredAt       time.Time                                `json:"occurredAt"`
}

type personaRelationshipReceiptStateDTO struct {
	PairID       string    `json:"pairId"`
	Version      int64     `json:"version"`
	IsFollowing  bool      `json:"isFollowing"`
	IsFollowedBy bool      `json:"isFollowedBy"`
	IsMutual     bool      `json:"isMutual"`
	IsBlocked    bool      `json:"isBlocked"`
	IsBlockedBy  bool      `json:"isBlockedBy"`
	UpdatedAt    time.Time `json:"updatedAt"`
}

type personaRelationshipReceiptDirectionDTO struct {
	PairID          string     `json:"pairId"`
	SourcePersonaID string     `json:"sourcePersonaId"`
	TargetPersonaID string     `json:"targetPersonaId"`
	Following       bool       `json:"following"`
	Blocked         bool       `json:"blocked"`
	FollowSource    string     `json:"followSource,omitempty"`
	FollowedAt      *time.Time `json:"followedAt,omitempty"`
	BlockedAt       *time.Time `json:"blockedAt,omitempty"`
	UpdatedAt       time.Time  `json:"updatedAt"`
}

func encodePersonaRelationshipReceipt(result relmodel.MutationResult) ([]byte, error) {
	cleared := make([]personaRelationshipReceiptDirectionDTO, 0, len(result.ClearedFollowing))
	for _, direction := range result.ClearedFollowing {
		cleared = append(cleared, personaRelationshipReceiptDirectionDTO{
			PairID:          direction.PairID,
			SourcePersonaID: direction.SourcePersonaID,
			TargetPersonaID: direction.TargetPersonaID,
			Following:       direction.Following,
			Blocked:         direction.Blocked,
			FollowSource:    direction.FollowSource,
			FollowedAt:      direction.FollowedAt,
			BlockedAt:       direction.BlockedAt,
			UpdatedAt:       direction.UpdatedAt,
		})
	}
	return json.Marshal(personaRelationshipReceiptDTO{
		State: personaRelationshipReceiptStateDTO{
			PairID:       result.State.PairID,
			Version:      result.State.Version,
			IsFollowing:  result.State.IsFollowing,
			IsFollowedBy: result.State.IsFollowedBy,
			IsMutual:     result.State.IsMutual,
			IsBlocked:    result.State.IsBlocked,
			IsBlockedBy:  result.State.IsBlockedBy,
			UpdatedAt:    result.State.UpdatedAt,
		},
		ClearedFollowing: cleared,
		Changed:          result.Changed,
		EventName:        result.EventName,
		OccurredAt:       result.OccurredAt,
	})
}

func decodePersonaRelationshipReceipt(payload []byte) (relmodel.MutationResult, error) {
	var receipt personaRelationshipReceiptDTO
	if err := json.Unmarshal(payload, &receipt); err != nil {
		return relmodel.MutationResult{}, err
	}
	cleared := make([]relmodel.Direction, 0, len(receipt.ClearedFollowing))
	for _, direction := range receipt.ClearedFollowing {
		cleared = append(cleared, relmodel.Direction{
			PairID:          direction.PairID,
			SourcePersonaID: direction.SourcePersonaID,
			TargetPersonaID: direction.TargetPersonaID,
			Following:       direction.Following,
			Blocked:         direction.Blocked,
			FollowSource:    direction.FollowSource,
			FollowedAt:      direction.FollowedAt,
			BlockedAt:       direction.BlockedAt,
			UpdatedAt:       direction.UpdatedAt,
		})
	}
	if len(cleared) == 0 {
		cleared = nil
	}
	return relmodel.MutationResult{
		State: relmodel.RelationshipState{
			PairID:       receipt.State.PairID,
			Version:      receipt.State.Version,
			IsFollowing:  receipt.State.IsFollowing,
			IsFollowedBy: receipt.State.IsFollowedBy,
			IsMutual:     receipt.State.IsMutual,
			IsBlocked:    receipt.State.IsBlocked,
			IsBlockedBy:  receipt.State.IsBlockedBy,
			UpdatedAt:    receipt.State.UpdatedAt,
		},
		ClearedFollowing: cleared,
		Changed:          receipt.Changed,
		EventName:        receipt.EventName,
		OccurredAt:       receipt.OccurredAt,
	}, nil
}

func lockPair(ctx context.Context, tx pgx.Tx, pair relmodel.Pair, _ relmodel.CommandKind) (int64, bool, error) {
	// Every newly accepted decision, including unset/no-op, materializes a Pair
	// row so the aggregate owns a sortable version fence.
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationships (
			pair_id, lower_persona_id, upper_persona_id, version, created_at, updated_at
		) VALUES ($1, $2, $3, 0, NOW(), NOW())
		ON CONFLICT (lower_persona_id, upper_persona_id) DO NOTHING`,
		pair.ID, pair.LowerPersonaID, pair.UpperPersonaID); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" && pgErr.ConstraintName == "persona_relationships_pkey" {
			return 0, false, relmodel.ErrPairIdentityConflict
		}
		return 0, false, fmt.Errorf("ensure persona relationship pair: %w", err)
	}
	var (
		version     int64
		storedLower string
		storedUpper string
	)
	err := tx.QueryRow(ctx, `
		SELECT version, lower_persona_id, upper_persona_id
		FROM persona_relationships WHERE pair_id = $1 FOR UPDATE`, pair.ID,
	).Scan(&version, &storedLower, &storedUpper)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, fmt.Errorf("lock persona relationship pair: %w", err)
	}
	// 摘要命中不等于身份相同。核验二元组后才允许写入，否则 digest 碰撞会把
	// 方向、计数与成功事件改写到另一对真实身份上。
	if err := pair.VerifyStoredIdentity(storedLower, storedUpper); err != nil {
		return 0, false, err
	}
	return version, true, nil
}

func loadLockedDirections(ctx context.Context, tx pgx.Tx, pairID string) (map[string]relmodel.Direction, error) {
	rows, err := tx.Query(ctx, `
		SELECT pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		FROM persona_relationship_directions
		WHERE pair_id = $1 FOR UPDATE`, pairID)
	if err != nil {
		return nil, fmt.Errorf("load persona relationship directions: %w", err)
	}
	defer rows.Close()
	directions := make(map[string]relmodel.Direction, 2)
	for rows.Next() {
		direction, err := scanDirection(rows)
		if err != nil {
			return nil, err
		}
		directions[direction.SourcePersonaID] = direction
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship directions: %w", err)
	}
	return directions, nil
}

func applyCommand(
	command relmodel.Command,
	pair relmodel.Pair,
	version int64,
	directions map[string]relmodel.Direction,
) (relmodel.MutationResult, []relmodel.Direction, error) {
	now := time.Now().UTC()
	result := relmodel.MutationResult{
		OccurredAt: now,
		State:      relationshipState(pair.ID, version, command.SourcePersonaID, command.TargetPersonaID, directions, now),
	}
	source := directions[command.SourcePersonaID]
	if source.SourcePersonaID == "" {
		source = relmodel.Direction{
			PairID:          pair.ID,
			SourcePersonaID: command.SourcePersonaID,
			TargetPersonaID: command.TargetPersonaID,
			UpdatedAt:       now,
		}
	}
	dirty := make([]relmodel.Direction, 0, 2)

	switch command.Kind {
	case relmodel.CommandFollow:
		for _, direction := range directions {
			if direction.Blocked {
				return relmodel.MutationResult{}, nil, relmodel.ErrFollowBlocked
			}
		}
		if !source.Following {
			source.Following = true
			source.FollowSource = normalizedFollowSource(command.FollowSource)
			source.FollowedAt = &now
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaFollowStateChanged"
		}
	case relmodel.CommandUnfollow:
		if source.SourcePersonaID != "" && source.Following {
			source.Following = false
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaFollowStateChanged"
		}
	case relmodel.CommandBlock:
		if !source.Blocked {
			source.Blocked = true
			source.BlockedAt = &now
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
		}
		for actorID, direction := range directions {
			if !direction.Following {
				continue
			}
			result.ClearedFollowing = append(result.ClearedFollowing, direction)
			direction.Following = false
			direction.UpdatedAt = now
			directions[actorID] = direction
			dirty = upsertDirtyDirection(dirty, direction)
			result.Changed = true
		}
		if result.Changed {
			result.EventName = "PersonaBlocked"
		}
	case relmodel.CommandUnblock:
		if source.SourcePersonaID != "" && source.Blocked {
			source.Blocked = false
			source.BlockedAt = nil
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaUnblocked"
		}
	default:
		return relmodel.MutationResult{}, nil, fmt.Errorf("unsupported persona relationship command %q", command.Kind)
	}
	if result.Changed {
		result.State = relationshipState(pair.ID, version+1, command.SourcePersonaID, command.TargetPersonaID, directions, now)
	}
	return result, dirty, nil
}

func upsertDirtyDirection(values []relmodel.Direction, next relmodel.Direction) []relmodel.Direction {
	for index := range values {
		if values[index].SourcePersonaID == next.SourcePersonaID {
			values[index] = next
			return values
		}
	}
	return append(values, next)
}

func normalizedFollowSource(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "profile"
	}
	return value
}

func relationshipState(
	pairID string,
	version int64,
	viewerPersonaID, targetPersonaID string,
	directions map[string]relmodel.Direction,
	updatedAt time.Time,
) relmodel.RelationshipState {
	viewer := directions[viewerPersonaID]
	target := directions[targetPersonaID]
	return relmodel.RelationshipState{
		PairID:       pairID,
		Version:      version,
		IsFollowing:  viewer.Following,
		IsFollowedBy: target.Following,
		IsMutual:     viewer.Following && target.Following,
		IsBlocked:    viewer.Blocked,
		IsBlockedBy:  target.Blocked,
		UpdatedAt:    updatedAt,
	}
}

func upsertDirection(ctx context.Context, tx pgx.Tx, direction relmodel.Direction) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_directions (
			pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
		ON CONFLICT (pair_id, source_persona_id) DO UPDATE SET
			target_persona_id = EXCLUDED.target_persona_id,
			following = EXCLUDED.following,
			blocked = EXCLUDED.blocked,
			follow_source = EXCLUDED.follow_source,
			followed_at = EXCLUDED.followed_at,
			blocked_at = EXCLUDED.blocked_at,
			updated_at = EXCLUDED.updated_at`,
		direction.PairID,
		direction.SourcePersonaID,
		direction.TargetPersonaID,
		direction.Following,
		direction.Blocked,
		nullableString(direction.FollowSource),
		direction.FollowedAt,
		direction.BlockedAt,
		direction.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert persona relationship direction: %w", err)
	}
	return nil
}

func appendOutbox(
	ctx context.Context,
	tx pgx.Tx,
	pairID string,
	version int64,
	command relmodel.Command,
	result relmodel.MutationResult,
) error {
	sourceFollowCleared, targetFollowCleared := clearedFollowDirections(
		command,
		result.ClearedFollowing,
	)
	payload, err := json.Marshal(relmodel.OutboxPayload{
		PairID:                  pairID,
		SourcePersonaID:         command.SourcePersonaID,
		TargetPersonaID:         command.TargetPersonaID,
		Following:               result.State.IsFollowing,
		SourceFollowCleared:     sourceFollowCleared,
		TargetFollowCleared:     targetFollowCleared,
		ClearedFollowDirections: len(result.ClearedFollowing),
		Version:                 version,
		OccurredAt:              result.OccurredAt,
	})
	if err != nil {
		return fmt.Errorf("marshal persona relationship outbox: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO persona_relationship_outbox (
			event_id, aggregate_id, aggregate_version, event_name, payload_json, occurred_at
		) VALUES ($1,$2,$3,$4,$5,$6)`,
		uuid.NewString(), pairID, version, result.EventName, payload, result.OccurredAt,
	)
	if err != nil {
		return fmt.Errorf("append persona relationship outbox: %w", err)
	}
	return nil
}

func clearedFollowDirections(
	command relmodel.Command,
	directions []relmodel.Direction,
) (sourceCleared bool, targetCleared bool) {
	for _, direction := range directions {
		switch {
		case direction.SourcePersonaID == command.SourcePersonaID &&
			direction.TargetPersonaID == command.TargetPersonaID:
			sourceCleared = true
		case direction.SourcePersonaID == command.TargetPersonaID &&
			direction.TargetPersonaID == command.SourcePersonaID:
			targetCleared = true
		}
	}
	return sourceCleared, targetCleared
}

func (s *PgPersonaRelationshipStore) ClaimPendingOutbox(
	ctx context.Context,
	owner string,
	lease time.Duration,
	limit int,
) ([]relmodel.OutboxEvent, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	owner = strings.TrimSpace(owner)
	if owner == "" {
		return nil, errors.New("persona relationship outbox claim owner is required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	leaseBefore := time.Now().UTC().Add(-lease)
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT candidate.event_id
			FROM persona_relationship_outbox AS candidate
			WHERE candidate.published_at IS NULL
				AND (candidate.claim_owner IS NULL OR candidate.claimed_at < $2)
				AND NOT EXISTS (
					SELECT 1
					FROM persona_relationship_outbox AS earlier
					WHERE earlier.aggregate_id = candidate.aggregate_id
						AND earlier.published_at IS NULL
						AND earlier.aggregate_version < candidate.aggregate_version
				)
			ORDER BY candidate.occurred_at, candidate.event_id
			LIMIT $3
			FOR UPDATE SKIP LOCKED
		)
		UPDATE persona_relationship_outbox AS outbox
		SET claim_owner = $1, claimed_at = NOW()
		FROM candidates
		WHERE outbox.event_id = candidates.event_id
		RETURNING outbox.event_id, outbox.event_name, outbox.payload_json`, owner, leaseBefore, limit)
	if err != nil {
		return nil, fmt.Errorf("claim pending persona relationship outbox: %w", err)
	}
	defer rows.Close()
	events := make([]relmodel.OutboxEvent, 0, limit)
	for rows.Next() {
		var (
			event   relmodel.OutboxEvent
			payload []byte
		)
		if err := rows.Scan(&event.EventID, &event.EventName, &payload); err != nil {
			return nil, fmt.Errorf("scan claimed persona relationship outbox: %w", err)
		}
		if err := json.Unmarshal(payload, &event.Payload); err != nil {
			return nil, fmt.Errorf("decode claimed persona relationship outbox payload: %w", err)
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate claimed persona relationship outbox: %w", err)
	}
	return events, nil
}

func (s *PgPersonaRelationshipStore) MarkOutboxPublished(ctx context.Context, eventID, owner string) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE persona_relationship_outbox
		SET published_at = NOW(), claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`, eventID, owner)
	if err != nil {
		return fmt.Errorf("mark persona relationship outbox published: %w", err)
	}
	if command.RowsAffected() != 1 {
		return fmt.Errorf("%w: event %q", relports.ErrOutboxClaimLost, eventID)
	}
	return nil
}

func (s *PgPersonaRelationshipStore) ReleaseOutboxClaim(ctx context.Context, eventID, owner string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE persona_relationship_outbox
		SET claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`, eventID, owner)
	if err != nil {
		return fmt.Errorf("release persona relationship outbox claim: %w", err)
	}
	return nil
}

func saveReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command relmodel.Command,
	pairID string,
	version int64,
	result relmodel.MutationResult,
) error {
	if command.IdempotencyKey == "" {
		return relmodel.ErrIdempotencyKeyRequired
	}
	payload, err := encodePersonaRelationshipReceipt(result)
	if err != nil {
		return fmt.Errorf("marshal persona relationship receipt: %w", err)
	}
	outcome := result.Outcome
	if outcome == "" {
		outcome = relmodel.OutcomeCommitted
	}
	// committed 必须落在某个 Pair 上；expired 与「目标不存在」的收敛没有 Pair，
	// 由 CHECK 约束一起保证不会写出半截结果。
	var storedPairID *string
	if outcome == relmodel.OutcomeCommitted && strings.TrimSpace(pairID) != "" {
		trimmed := strings.TrimSpace(pairID)
		storedPairID = &trimmed
	}
	if outcome == relmodel.OutcomeCommitted && storedPairID == nil {
		outcome = relmodel.OutcomeRejected
	}
	acceptUntil := command.AcceptUntil
	if acceptUntil.IsZero() {
		acceptUntil = result.OccurredAt.Add(basisAcceptWindow)
	}
	createdAt := time.Now().UTC()
	expiresAt := receiptRetentionDeadline(acceptUntil)
	if minimum := createdAt.Add(96 * time.Hour); expiresAt.Before(minimum) {
		expiresAt = minimum
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO persona_relationship_command_receipts (
			receipt_id, actor_persona_id, idempotency_key, operation, target_persona_id,
			pair_id, aggregate_version, response_json, outcome, command_digest,
			basis_digest, accept_until, expires_at, finalized_at, created_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)`,
		uuid.NewString(), command.SourcePersonaID, command.IdempotencyKey,
		string(command.Kind), command.TargetPersonaID, storedPairID, version, payload,
		string(outcome), relationshipCommandDigest(command),
		relationshipBasisDigest(command.MutationBasis),
		acceptUntil, expiresAt, result.OccurredAt, createdAt,
	)
	if err != nil {
		return fmt.Errorf("save persona relationship receipt: %w", err)
	}
	return nil
}

// receiptRetentionDeadline 是 receipt 的最短保留期限：覆盖 72h 接受窗口
// 之后仍留恢复余量，首期下限 96h。
func receiptRetentionDeadline(acceptUntil time.Time) time.Time {
	return acceptUntil.Add(24 * time.Hour)
}

// relationshipCommandDigest 冻结命令的业务身份；同键不同命令即冲突。
func relationshipCommandDigest(command relmodel.Command) string {
	expectedVersion := "unset"
	if command.ExpectedVersion != nil {
		expectedVersion = fmt.Sprintf("%d", *command.ExpectedVersion)
	}
	digest := sha256.Sum256([]byte(strings.Join([]string{
		string(command.Kind),
		command.SourcePersonaID,
		command.TargetPersonaID,
		expectedVersion,
	}, "\x1f")))
	return hex.EncodeToString(digest[:])
}

// relationshipBasisDigest 只保存依据摘要，不落 token 原文。
func relationshipBasisDigest(basis string) string {
	basis = strings.TrimSpace(basis)
	if basis == "" {
		return ""
	}
	digest := sha256.Sum256([]byte(basisSignatureDomain + "\x1f" + basis))
	return hex.EncodeToString(digest[:])
}

func (s *PgPersonaRelationshipStore) Get(
	ctx context.Context,
	viewerPersonaID, targetPersonaID string,
) (relmodel.RelationshipState, error) {
	pair, err := relmodel.NewPair(viewerPersonaID, targetPersonaID)
	if err != nil {
		return relmodel.RelationshipState{}, err
	}
	// 版本与两个方向必须来自同一个快照。分两条 SQL 读会让并发提交产生混合
	// 快照：旧版本配新方向，或新版本配旧方向。
	rows, err := s.pool.Query(ctx, `
		SELECT pair.version, pair.updated_at, pair.lower_persona_id, pair.upper_persona_id,
			direction.source_persona_id, direction.target_persona_id,
			direction.following, direction.blocked,
			direction.follow_source, direction.followed_at, direction.blocked_at,
			direction.updated_at
		FROM persona_relationships AS pair
		LEFT JOIN persona_relationship_directions AS direction
			ON direction.pair_id = pair.pair_id
		WHERE pair.pair_id = $1`, pair.ID)
	if err != nil {
		return relmodel.RelationshipState{}, fmt.Errorf("read persona relationship: %w", err)
	}
	defer rows.Close()
	var (
		version    int64
		updatedAt  time.Time
		found      bool
		directions = make(map[string]relmodel.Direction, 2)
	)
	for rows.Next() {
		var (
			storedLower  string
			storedUpper  string
			source       *string
			target       *string
			following    *bool
			blocked      *bool
			followSource *string
			followedAt   *time.Time
			blockedAt    *time.Time
			directionAt  *time.Time
		)
		if err := rows.Scan(
			&version, &updatedAt, &storedLower, &storedUpper,
			&source, &target, &following, &blocked,
			&followSource, &followedAt, &blockedAt, &directionAt,
		); err != nil {
			return relmodel.RelationshipState{}, fmt.Errorf("scan persona relationship snapshot: %w", err)
		}
		if err := pair.VerifyStoredIdentity(storedLower, storedUpper); err != nil {
			return relmodel.RelationshipState{}, err
		}
		found = true
		if source == nil || target == nil {
			continue
		}
		direction := relmodel.Direction{
			PairID:          pair.ID,
			SourcePersonaID: *source,
			TargetPersonaID: *target,
		}
		if following != nil {
			direction.Following = *following
		}
		if blocked != nil {
			direction.Blocked = *blocked
		}
		if followSource != nil {
			direction.FollowSource = *followSource
		}
		direction.FollowedAt = followedAt
		direction.BlockedAt = blockedAt
		if directionAt != nil {
			direction.UpdatedAt = *directionAt
		}
		directions[direction.SourcePersonaID] = direction
	}
	if err := rows.Err(); err != nil {
		return relmodel.RelationshipState{}, fmt.Errorf("iterate persona relationship snapshot: %w", err)
	}
	if !found {
		return relmodel.RelationshipState{}, nil
	}
	return relationshipState(pair.ID, version, viewerPersonaID, targetPersonaID, directions, updatedAt), nil
}

// GetMany 以一次查询取回 viewer 与一组 target 的关系快照。
// 每个 pair 的两个方向在同一行集合内解析，因此不会出现「viewer 方向来自新
// 快照、target 方向来自旧快照」的混合结果。
func (s *PgPersonaRelationshipStore) GetMany(
	ctx context.Context,
	viewerPersonaID string,
	targetPersonaIDs []string,
) (map[string]relmodel.RelationshipState, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	states := make(map[string]relmodel.RelationshipState, len(targetPersonaIDs))
	if viewerPersonaID == "" || len(targetPersonaIDs) == 0 {
		return states, nil
	}
	// pair 身份由 viewer 与 target 的规范化二元组决定；先在内存里算出本次
	// 需要的 pair 集合，再用一次 IN 查询取回两个方向。
	pairByID := make(map[string]relmodel.Pair, len(targetPersonaIDs))
	targetByPairID := make(map[string]string, len(targetPersonaIDs))
	pairIDs := make([]string, 0, len(targetPersonaIDs))
	for _, targetPersonaID := range targetPersonaIDs {
		targetPersonaID = strings.TrimSpace(targetPersonaID)
		if targetPersonaID == "" || targetPersonaID == viewerPersonaID {
			continue
		}
		if _, seen := states[targetPersonaID]; seen {
			continue
		}
		states[targetPersonaID] = relmodel.RelationshipState{}
		pair, err := relmodel.NewPair(viewerPersonaID, targetPersonaID)
		if err != nil {
			return nil, err
		}
		if _, exists := pairByID[pair.ID]; exists {
			continue
		}
		pairByID[pair.ID] = pair
		targetByPairID[pair.ID] = targetPersonaID
		pairIDs = append(pairIDs, pair.ID)
	}
	if len(pairIDs) == 0 {
		return states, nil
	}

	rows, err := s.pool.Query(ctx, `
		SELECT pair.pair_id, pair.version, pair.updated_at,
			pair.lower_persona_id, pair.upper_persona_id,
			direction.source_persona_id, direction.target_persona_id,
			direction.following, direction.blocked
		FROM persona_relationships AS pair
		LEFT JOIN persona_relationship_directions AS direction
			ON direction.pair_id = pair.pair_id
		WHERE pair.pair_id = ANY($1)`, pairIDs)
	if err != nil {
		return nil, fmt.Errorf("read persona relationship batch: %w", err)
	}
	defer rows.Close()

	type pairSnapshot struct {
		version    int64
		updatedAt  time.Time
		directions map[string]relmodel.Direction
	}
	snapshots := make(map[string]*pairSnapshot, len(pairIDs))
	for rows.Next() {
		var (
			pairID      string
			version     int64
			updatedAt   time.Time
			storedLower string
			storedUpper string
			source      *string
			target      *string
			following   *bool
			blocked     *bool
		)
		if err := rows.Scan(
			&pairID, &version, &updatedAt, &storedLower, &storedUpper,
			&source, &target, &following, &blocked,
		); err != nil {
			return nil, fmt.Errorf("scan persona relationship batch: %w", err)
		}
		pair, known := pairByID[pairID]
		if !known {
			continue
		}
		if err := pair.VerifyStoredIdentity(storedLower, storedUpper); err != nil {
			return nil, err
		}
		snapshot, exists := snapshots[pairID]
		if !exists {
			snapshot = &pairSnapshot{
				version:    version,
				updatedAt:  updatedAt,
				directions: make(map[string]relmodel.Direction, 2),
			}
			snapshots[pairID] = snapshot
		}
		if source == nil || target == nil {
			continue
		}
		direction := relmodel.Direction{
			PairID:          pairID,
			SourcePersonaID: *source,
			TargetPersonaID: *target,
		}
		if following != nil {
			direction.Following = *following
		}
		if blocked != nil {
			direction.Blocked = *blocked
		}
		snapshot.directions[direction.SourcePersonaID] = direction
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship batch: %w", err)
	}
	for pairID, snapshot := range snapshots {
		targetPersonaID := targetByPairID[pairID]
		states[targetPersonaID] = relationshipState(
			pairID,
			snapshot.version,
			viewerPersonaID,
			targetPersonaID,
			snapshot.directions,
			snapshot.updatedAt,
		)
	}
	return states, nil
}

func scanDirection(row pgx.Row) (relmodel.Direction, error) {
	var direction relmodel.Direction
	var followSource *string
	err := row.Scan(
		&direction.PairID,
		&direction.SourcePersonaID,
		&direction.TargetPersonaID,
		&direction.Following,
		&direction.Blocked,
		&followSource,
		&direction.FollowedAt,
		&direction.BlockedAt,
		&direction.UpdatedAt,
	)
	if err != nil {
		return relmodel.Direction{}, fmt.Errorf("scan persona relationship direction: %w", err)
	}
	if followSource != nil {
		direction.FollowSource = *followSource
	}
	return direction, nil
}

func (s *PgPersonaRelationshipStore) ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int, viewerPersonaID, query string) ([]relmodel.Direction, string, error) {
	return s.listDirections(ctx, sourcePersonaID, cursor, limit, "source_persona_id", "target_persona_id", "following", "followed_at", viewerPersonaID, query)
}

func (s *PgPersonaRelationshipStore) ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int, viewerPersonaID, query string) ([]relmodel.Direction, string, error) {
	return s.listDirections(ctx, targetPersonaID, cursor, limit, "target_persona_id", "source_persona_id", "following", "followed_at", viewerPersonaID, query)
}

func (s *PgPersonaRelationshipStore) ListBlocked(
	ctx context.Context,
	sourcePersonaID, cursor string,
	limit int,
) ([]relports.BlockedListItem, string, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	claims := relationshipapp.ReadCursorClaims{
		OwnerPersonaID:  sourcePersonaID,
		ViewerPersonaID: sourcePersonaID,
		Direction:       "blocked",
	}
	args := []any{sourcePersonaID}
	where := "d.source_persona_id = $1 AND d.blocked = TRUE"
	if strings.TrimSpace(cursor) != "" {
		if s.cursorSigner == nil {
			return nil, "", relationshipapp.ErrInvalidReadCursor
		}
		position, err := s.cursorSigner.Verify(cursor, claims)
		if err != nil {
			return nil, "", err
		}
		args = append(args, position.PositionAt, position.PositionPairID)
		where += fmt.Sprintf(" AND (d.blocked_at, d.pair_id) < ($%d, $%d)", len(args)-1, len(args))
	}
	args = append(args, limit+1)
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
		SELECT d.pair_id, d.target_persona_id,
			COALESCE(NULLIF(p.display_name, ''), d.target_persona_id),
			COALESCE(NULLIF(p.user_handle, ''), d.target_persona_id),
			COALESCE(p.avatar_url, ''),
			d.blocked_at
		FROM persona_relationship_directions d
		LEFT JOIN personas p ON p.persona_id = d.target_persona_id
		WHERE %s
		ORDER BY d.blocked_at DESC, d.pair_id DESC
		LIMIT $%d`, where, len(args)), args...)
	if err != nil {
		return nil, "", fmt.Errorf("list blocked persona views: %w", err)
	}
	defer rows.Close()

	type blockedRow struct {
		pairID string
		item   relports.BlockedListItem
	}
	items := make([]blockedRow, 0, limit+1)
	for rows.Next() {
		var row blockedRow
		if err := rows.Scan(
			&row.pairID,
			&row.item.TargetPersonaID,
			&row.item.DisplayName,
			&row.item.UserHandle,
			&row.item.AvatarURL,
			&row.item.BlockedAt,
		); err != nil {
			return nil, "", fmt.Errorf("scan blocked persona view: %w", err)
		}
		row.item.BlockedAt = row.item.BlockedAt.UTC()
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		return nil, "", fmt.Errorf("iterate blocked persona views: %w", err)
	}

	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		claims.PositionAt = last.item.BlockedAt.UTC()
		claims.PositionPairID = last.pairID
		var err error
		nextCursor, err = s.cursorSigner.Issue(claims)
		if err != nil {
			return nil, "", err
		}
	}
	result := make([]relports.BlockedListItem, 0, len(items))
	for _, row := range items {
		result = append(result, row.item)
	}
	return result, nextCursor, nil
}

func (s *PgPersonaRelationshipStore) listDirections(
	ctx context.Context,
	personaID, cursor string,
	limit int,
	personaColumn, peerColumn, activeColumn, orderColumn string,
	viewerPersonaID, searchQuery string,
) ([]relmodel.Direction, string, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	if deadline, ok := ctx.Deadline(); !ok || time.Until(deadline) > 1500*time.Millisecond {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, 1500*time.Millisecond)
		defer cancel()
	}
	searchQuery = strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(searchQuery))), " ")
	direction := "followers"
	if personaColumn == "source_persona_id" {
		direction = "following"
	}
	claims := relationshipapp.ReadCursorClaims{
		OwnerPersonaID: personaID, ViewerPersonaID: viewerPersonaID,
		Direction: direction, Query: searchQuery,
	}
	args := []any{personaID}
	where := "d." + personaColumn + " = $1 AND d." + activeColumn + " = TRUE"
	if strings.TrimSpace(cursor) != "" {
		if s.cursorSigner == nil {
			return nil, "", relationshipapp.ErrInvalidReadCursor
		}
		position, err := s.cursorSigner.Verify(cursor, claims)
		if err != nil {
			return nil, "", err
		}
		args = append(args, position.PositionAt, position.PositionPairID)
		where += fmt.Sprintf(" AND (d.%s, d.pair_id) < ($%d, $%d)", orderColumn, len(args)-1, len(args))
	}
	from := "persona_relationship_directions AS d"
	if searchQuery != "" {
		from += " JOIN persona_public_profile_search AS p ON p.persona_id = d." + peerColumn
		args = append(args, searchQuery)
		where += fmt.Sprintf(" AND p.search_document ILIKE '%%' || $%d || '%%'", len(args))
	}
	// viewer safety is applied in the same graph query, so hidden rows cannot
	// force application-layer overfetch/fill scans.
	if strings.TrimSpace(viewerPersonaID) != "" {
		args = append(args, viewerPersonaID)
		where += fmt.Sprintf(` AND NOT EXISTS (
			SELECT 1 FROM persona_relationship_directions AS safety
			WHERE safety.blocked = TRUE
			  AND ((safety.source_persona_id = $%d AND safety.target_persona_id = d.%s)
			    OR (safety.target_persona_id = $%d AND safety.source_persona_id = d.%s))
		)`, len(args), peerColumn, len(args), peerColumn)
	}
	args = append(args, limit+1)
	sqlQuery := fmt.Sprintf(`
		SELECT d.pair_id, d.source_persona_id, d.target_persona_id, d.following, d.blocked,
			d.follow_source, d.followed_at, d.blocked_at, d.updated_at
		FROM %s
		WHERE %s
		ORDER BY d.%s DESC, d.pair_id DESC
		LIMIT $%d`, from, where, orderColumn, len(args))
	rows, err := s.pool.Query(ctx, sqlQuery, args...)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, "", fmt.Errorf("relationship read deadline exceeded: %w", context.DeadlineExceeded)
		}
		return nil, "", fmt.Errorf("list persona relationship directions: %w", err)
	}
	defer rows.Close()
	items := make([]relmodel.Direction, 0, limit+1)
	for rows.Next() {
		item, err := scanDirection(rows)
		if err != nil {
			return nil, "", err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, "", fmt.Errorf("iterate persona relationship list: %w", err)
	}
	if len(items) <= limit {
		return items, "", nil
	}
	items = items[:limit]
	last := items[len(items)-1]
	if last.FollowedAt == nil || s.cursorSigner == nil {
		return nil, "", relationshipapp.ErrInvalidReadCursor
	}
	claims.PositionAt = last.FollowedAt.UTC()
	claims.PositionPairID = last.PairID
	next, err := s.cursorSigner.Issue(claims)
	if err != nil {
		return nil, "", err
	}
	return items, next, nil
}

func nullableString(value string) *string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return &value
}

// FollowPolicyActivation is the only production input to the authoritative
// relationship policy row. The digest binds policy/revision/limit so an
// environment cannot activate a partially rendered configuration.
type FollowPolicyActivation struct {
	Revision               int64
	MaxFollowingPerPersona int
	ConfigDigest           string
}

func (s *PgPersonaRelationshipStore) ActivateFollowPolicy(ctx context.Context, next FollowPolicyActivation) error {
	if s == nil || s.pool == nil {
		return errors.New("relationship store unavailable")
	}
	if next.Revision < 1 || next.MaxFollowingPerPersona < 1 {
		return relmodel.ErrFollowPolicyUnavailable
	}
	expected := sha256.Sum256([]byte(fmt.Sprintf("%s\x1f%d\x1f%d", followPolicyID, next.Revision, next.MaxFollowingPerPersona)))
	if strings.ToLower(strings.TrimSpace(next.ConfigDigest)) != hex.EncodeToString(expected[:]) {
		return fmt.Errorf("%w: policy digest mismatch", relmodel.ErrFollowPolicyUnavailable)
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var currentRevision int64
	err = tx.QueryRow(ctx, `SELECT revision FROM relationship_policy_activation WHERE policy_id=$1 FOR UPDATE`, followPolicyID).Scan(&currentRevision)
	if errors.Is(err, pgx.ErrNoRows) {
		_, err = tx.Exec(ctx, `INSERT INTO relationship_policy_activation(policy_id,revision,max_following_per_persona,config_digest,activated_at) VALUES($1,$2,$3,$4,NOW())`, followPolicyID, next.Revision, next.MaxFollowingPerPersona, next.ConfigDigest)
	} else if err == nil {
		if next.Revision < currentRevision {
			return fmt.Errorf("%w: policy revision rollback", relmodel.ErrFollowPolicyUnavailable)
		}
		if next.Revision == currentRevision {
			var limit int
			var digest string
			if e := tx.QueryRow(ctx, `SELECT max_following_per_persona,config_digest FROM relationship_policy_activation WHERE policy_id=$1`, followPolicyID).Scan(&limit, &digest); e != nil {
				return e
			}
			if limit != next.MaxFollowingPerPersona || digest != next.ConfigDigest {
				return fmt.Errorf("%w: same revision different policy", relmodel.ErrFollowPolicyUnavailable)
			}
		} else {
			_, err = tx.Exec(ctx, `UPDATE relationship_policy_activation SET revision=$2,max_following_per_persona=$3,config_digest=$4,activated_at=NOW() WHERE policy_id=$1`, followPolicyID, next.Revision, next.MaxFollowingPerPersona, next.ConfigDigest)
		}
	}
	if err != nil {
		return err
	}
	return tx.Commit(ctx)
}
