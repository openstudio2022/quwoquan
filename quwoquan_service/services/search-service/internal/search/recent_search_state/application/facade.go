// Package recentsearch 是 RecentSearchState 的应用门面：
// 命名 set 操作由服务端加载当前 version 做内部 CAS + 有限重放；
// 目标状态已满足时持久化 no-op receipt；公开请求不携带版本字段。
package recentsearch

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/ports"
)

const (
	moduleSearch      = rterrors.ModuleSearch
	ReceiptTTLSeconds = 24 * 60 * 60
	maxAttempts       = 3
)

// Facade 绑定 RecentSearchState 聚合 owner。
type Facade struct {
	store ports.Store
	now   func() time.Time
}

func NewFacade(store ports.Store) (*Facade, error) {
	if store == nil {
		return nil, errors.New("recent search store is required")
	}
	return &Facade{store: store, now: time.Now}, nil
}

// UpsertCommand 只携带命名意图；entryId/version 由服务端派生。
type UpsertCommand struct {
	PersonaID      string
	Scope          string
	Facet          string
	Query          string
	IdempotencyKey string
}

type DeleteCommand struct {
	PersonaID      string
	EntryID        string
	IdempotencyKey string
}

type ClearCommand struct {
	PersonaID      string
	Scope          string
	IdempotencyKey string
}

// Result 是命令回执视图。
type Result struct {
	Entry    model.Entry
	Version  int64
	Replayed bool
}

// List 返回 persona 的最近搜索（可按 scope 收窄），按最近使用倒序。
func (f *Facade) List(ctx context.Context, personaID, scope string) ([]model.Entry, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, unauthorized()
	}
	scope = strings.TrimSpace(scope)
	var states []model.State
	if scope != "" {
		state, found, err := f.store.Load(ctx, personaID, scope)
		if err != nil {
			return nil, storageFailed(err)
		}
		if found {
			states = append(states, state)
		}
	} else {
		all, err := f.store.ListByPersona(ctx, personaID)
		if err != nil {
			return nil, storageFailed(err)
		}
		states = all
	}
	entries := make([]model.Entry, 0, model.MaxEntries)
	for _, state := range states {
		entries = append(entries, state.Entries...)
	}
	sort.SliceStable(entries, func(i, j int) bool {
		return entries[i].UpdatedAt.After(entries[j].UpdatedAt)
	})
	if len(entries) > model.MaxEntries {
		entries = entries[:model.MaxEntries]
	}
	return entries, nil
}

// Upsert 记录/提升一条最近搜索。
func (f *Facade) Upsert(ctx context.Context, command UpsertCommand) (Result, error) {
	personaID := strings.TrimSpace(command.PersonaID)
	if personaID == "" {
		return Result{}, unauthorized()
	}
	if model.NormalizeQuery(command.Query) == "" {
		return Result{}, invalidArgument("query is required")
	}
	receiptKey, digest, err := receiptIdentity(personaID, command.IdempotencyKey, "upsert",
		model.NormalizeScope(command.Scope), strings.TrimSpace(command.Facet), model.NormalizeQuery(command.Query))
	if err != nil {
		return Result{}, err
	}
	if replayed, found, err := f.replay(ctx, receiptKey, digest); err != nil || found {
		return replayed, err
	}
	scope := model.NormalizeScope(command.Scope)
	for attempt := 0; attempt < maxAttempts; attempt++ {
		state, found, loadErr := f.store.Load(ctx, personaID, scope)
		if loadErr != nil {
			return Result{}, storageFailed(loadErr)
		}
		if !found {
			state = model.NewState(personaID, scope, f.now())
		}
		expectedVersion := state.Version
		entry, changed, upsertErr := state.Upsert(command.Query, command.Facet, f.now())
		if upsertErr != nil {
			return Result{}, invalidArgument(upsertErr.Error())
		}
		if !changed {
			return f.recordNoop(
				ctx,
				personaID,
				receiptKey,
				digest,
				entry,
				expectedVersion,
			)
		}
		commitErr := f.store.Commit(ctx, ports.Commit{
			ExpectedVersion: expectedVersion,
			State:           state,
			Receipt: f.receipt(
				personaID,
				receiptKey,
				digest,
				entry,
				state.Version,
			),
		})
		if commitErr == nil {
			return Result{Entry: entry, Version: state.Version}, nil
		}
		if errors.Is(commitErr, ports.ErrIdempotencyConflict) {
			return Result{}, idempotencyConflict()
		}
		if !errors.Is(commitErr, ports.ErrVersionConflict) || attempt == maxAttempts-1 {
			if errors.Is(commitErr, ports.ErrVersionConflict) {
				return Result{}, versionConflict()
			}
			return Result{}, storageFailed(commitErr)
		}
	}
	panic("unreachable recent search upsert retry")
}

// Delete 删除单条最近搜索；目标不存在按 no-op receipt 重放安全。
func (f *Facade) Delete(ctx context.Context, command DeleteCommand) (Result, error) {
	personaID := strings.TrimSpace(command.PersonaID)
	if personaID == "" {
		return Result{}, unauthorized()
	}
	entryID := strings.TrimSpace(command.EntryID)
	if entryID == "" {
		return Result{}, invalidArgument("entryId is required")
	}
	receiptKey, digest, err := receiptIdentity(personaID, command.IdempotencyKey, "delete", entryID)
	if err != nil {
		return Result{}, err
	}
	if replayed, found, err := f.replay(ctx, receiptKey, digest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < maxAttempts; attempt++ {
		state, found, loadErr := f.store.FindEntryOwner(ctx, personaID, entryID)
		if loadErr != nil {
			return Result{}, storageFailed(loadErr)
		}
		if !found {
			return f.recordNoop(
				ctx,
				personaID,
				receiptKey,
				digest,
				model.Entry{EntryID: entryID},
				0,
			)
		}
		expectedVersion := state.Version
		if !state.Delete(entryID, f.now()) {
			return f.recordNoop(
				ctx,
				personaID,
				receiptKey,
				digest,
				model.Entry{EntryID: entryID},
				expectedVersion,
			)
		}
		commitErr := f.store.Commit(ctx, ports.Commit{
			ExpectedVersion: expectedVersion,
			State:           state,
			Receipt: f.receipt(
				personaID,
				receiptKey,
				digest,
				model.Entry{EntryID: entryID},
				state.Version,
			),
		})
		if commitErr == nil {
			return Result{Entry: model.Entry{EntryID: entryID}, Version: state.Version}, nil
		}
		if errors.Is(commitErr, ports.ErrIdempotencyConflict) {
			return Result{}, idempotencyConflict()
		}
		if !errors.Is(commitErr, ports.ErrVersionConflict) || attempt == maxAttempts-1 {
			if errors.Is(commitErr, ports.ErrVersionConflict) {
				return Result{}, versionConflict()
			}
			return Result{}, storageFailed(commitErr)
		}
	}
	panic("unreachable recent search delete retry")
}

// Clear 清空 persona 最近搜索（可按 scope 收窄）；已空按 no-op receipt 处理。
func (f *Facade) Clear(ctx context.Context, command ClearCommand) (Result, error) {
	personaID := strings.TrimSpace(command.PersonaID)
	if personaID == "" {
		return Result{}, unauthorized()
	}
	scope := model.NormalizeScope(command.Scope)
	receiptKey, digest, err := receiptIdentity(personaID, command.IdempotencyKey, "clear", scope)
	if err != nil {
		return Result{}, err
	}
	if replayed, found, err := f.replay(ctx, receiptKey, digest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < maxAttempts; attempt++ {
		state, found, loadErr := f.store.Load(ctx, personaID, scope)
		if loadErr != nil {
			return Result{}, storageFailed(loadErr)
		}
		if !found {
			return f.recordNoop(
				ctx,
				personaID,
				receiptKey,
				digest,
				model.Entry{},
				0,
			)
		}
		expectedVersion := state.Version
		if !state.Clear(f.now()) {
			return f.recordNoop(
				ctx,
				personaID,
				receiptKey,
				digest,
				model.Entry{},
				expectedVersion,
			)
		}
		commitErr := f.store.Commit(ctx, ports.Commit{
			ExpectedVersion: expectedVersion,
			State:           state,
			Receipt: f.receipt(
				personaID,
				receiptKey,
				digest,
				model.Entry{},
				state.Version,
			),
		})
		if commitErr == nil {
			return Result{Version: state.Version}, nil
		}
		if errors.Is(commitErr, ports.ErrIdempotencyConflict) {
			return Result{}, idempotencyConflict()
		}
		if !errors.Is(commitErr, ports.ErrVersionConflict) || attempt == maxAttempts-1 {
			if errors.Is(commitErr, ports.ErrVersionConflict) {
				return Result{}, versionConflict()
			}
			return Result{}, storageFailed(commitErr)
		}
	}
	panic("unreachable recent search clear retry")
}

func (f *Facade) replay(ctx context.Context, receiptKey, digest string) (Result, bool, error) {
	receipt, found, err := f.store.FindReceipt(ctx, receiptKey, digest)
	if err != nil {
		if errors.Is(err, ports.ErrIdempotencyConflict) {
			return Result{}, false, idempotencyConflict()
		}
		return Result{}, false, storageFailed(err)
	}
	if !found {
		return Result{}, false, nil
	}
	return Result{Entry: receipt.Entry, Version: receipt.StateVersion, Replayed: true}, true, nil
}

func (f *Facade) recordNoop(
	ctx context.Context,
	personaID string,
	receiptKey, digest string,
	entry model.Entry,
	version int64,
) (Result, error) {
	receipt, err := f.store.RecordNoopReceipt(
		ctx,
		f.receipt(personaID, receiptKey, digest, entry, version),
	)
	if err != nil {
		if errors.Is(err, ports.ErrIdempotencyConflict) {
			return Result{}, idempotencyConflict()
		}
		return Result{}, storageFailed(err)
	}
	return Result{Entry: receipt.Entry, Version: receipt.StateVersion, Replayed: receipt.Replayed}, nil
}

func (f *Facade) receipt(
	personaID string,
	receiptKey string,
	digest string,
	entry model.Entry,
	version int64,
) ports.Receipt {
	now := f.now().UTC()
	return ports.Receipt{
		ReceiptKey:    receiptKey,
		PersonaID:     strings.TrimSpace(personaID),
		CommandDigest: digest,
		Entry:         entry,
		StateVersion:  version,
		CreatedAt:     now,
		ExpiresAt:     now.Add(time.Duration(ReceiptTTLSeconds) * time.Second),
	}
}

// receiptIdentity 派生 actor-scoped receipt key 与 command digest。
func receiptIdentity(personaID, idempotencyKey, commandName string, parts ...string) (string, string, error) {
	rawKey := strings.TrimSpace(idempotencyKey)
	if rawKey == "" {
		return "", "", invalidArgument("Idempotency-Key is required")
	}
	keySum := sha256.Sum256([]byte(personaID + "\x00" + rawKey))
	digestSum := sha256.Sum256([]byte(commandName + "\x00" + strings.Join(parts, "\x00")))
	return "recent:" + hex.EncodeToString(keySum[:]), hex.EncodeToString(digestSum[:]), nil
}

func unauthorized() error {
	return rterrors.NewAppError(
		rterrors.NewCode(rterrors.ModuleGateway, rterrors.KindUser, "unauthorized"),
		"请先登录后再继续", "recent search requires an authenticated persona")
}

func invalidArgument(debug string) error {
	return rterrors.NewInvalidArgument(moduleSearch, "最近搜索请求参数不正确", debug)
}

// 以下错误的 code 与 http_status 均以 search/search/recent_search_state/errors.yaml 为真相源。

func versionConflict() error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleSearch, rterrors.KindUser, "recent_version_conflict"),
		"最近搜索已更新，请刷新后重试", "recent search state changed repeatedly while applying intent")
	appErr.HTTPStatus = 409
	return appErr
}

func idempotencyConflict() error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleSearch, rterrors.KindUser, "recent_idempotency_conflict"),
		"重复请求与原操作不一致，请刷新后重试", "idempotency key reused with a different recent search command")
	appErr.HTTPStatus = 409
	return appErr
}

func storageFailed(err error) error {
	var appErr *rterrors.AppError
	if errors.As(err, &appErr) {
		return appErr
	}
	failed := rterrors.NewAppError(
		rterrors.NewCode(moduleSearch, rterrors.KindSystem, "recent_storage_failed"),
		"最近搜索操作失败，请稍后重试", err.Error())
	failed.HTTPStatus = 500
	return failed
}
