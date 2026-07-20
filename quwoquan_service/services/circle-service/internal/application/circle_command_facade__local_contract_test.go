package application

import (
	"context"
	"errors"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	circlemodel "quwoquan_service/services/circle-service/internal/domain/circle/model"
	circleports "quwoquan_service/services/circle-service/internal/domain/circle/ports"
)

func commandContext(personaID, idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		Actor:          operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
		IdempotencyKey: idempotencyKey,
	})
}

func newFacadeUnderTest() (*CircleCommandFacade, *memoryCircleAggregateStore, *memoryRoleReader) {
	store := newMemoryCircleAggregateStore()
	roles := &memoryRoleReader{roles: map[string]string{}}
	facade := NewCircleCommandFacade(store, roles, nil, nil)
	return facade, store, roles
}

func TestCircleCreateIsIdempotentAndOwnerScoped(t *testing.T) {
	facade, store, _ := newFacadeUnderTest()

	created, err := facade.Create(commandContext("persona-owner", "create-1"), CreateCircleCommand{Name: "契约圈"})
	if err != nil {
		t.Fatalf("create circle: %v", err)
	}
	if created.Version != 1 || created.Status != circlemodel.CircleStatusActive || created.IdempotentReplay {
		t.Fatalf("create receipt drift: %+v", created)
	}
	circle, found, _ := store.Load(context.Background(), created.CircleID)
	if !found || circle.OwnerID != "persona-owner" || len(circle.SectionConfig) != 4 {
		t.Fatalf("aggregate state drift: found=%v %+v", found, circle)
	}

	replayed, err := facade.Create(commandContext("persona-owner", "create-1"), CreateCircleCommand{Name: "契约圈"})
	if err != nil || !replayed.IdempotentReplay || replayed.CircleID != created.CircleID {
		t.Fatalf("create replay drift: %+v err=%v", replayed, err)
	}

	if _, err := facade.Create(commandContext("persona-owner", "create-1"), CreateCircleCommand{Name: "另一个名字"}); !isCode(err, "CIRCLE.USER.circle_idempotency_conflict") {
		t.Fatalf("conflicting body must map idempotency conflict, got %v", err)
	}
}

func TestCircleUpdateEnforcesOwnerOrAdminBOLA(t *testing.T) {
	facade, _, roles := newFacadeUnderTest()
	created, err := facade.Create(commandContext("persona-owner", "create-bola"), CreateCircleCommand{Name: "权限圈"})
	if err != nil {
		t.Fatal(err)
	}
	name := "越权名"
	if _, err := facade.Update(commandContext("persona-outsider", "update-bola"), UpdateCircleCommand{CircleID: created.CircleID, Name: &name}); !isCode(err, "CIRCLE.USER.permission_denied") {
		t.Fatalf("outsider update must fail closed, got %v", err)
	}

	roles.roles[created.CircleID+"/persona-admin"] = "admin"
	adminName := "管理员改名"
	updated, err := facade.Update(commandContext("persona-admin", "update-admin"), UpdateCircleCommand{CircleID: created.CircleID, Name: &adminName})
	if err != nil || updated.Version != 2 {
		t.Fatalf("admin update drift: %+v err=%v", updated, err)
	}
}

func TestCircleUpdateRetriesPureVersionRace(t *testing.T) {
	facade, store, _ := newFacadeUnderTest()
	created, err := facade.Create(commandContext("persona-owner", "create-race"), CreateCircleCommand{Name: "竞态圈"})
	if err != nil {
		t.Fatal(err)
	}
	// 首次提交遇到纯竞态冲突；服务端应重载最新版本并重放意图。
	store.conflictOnce = true
	name := "竞态后的名字"
	updated, err := facade.Update(commandContext("persona-owner", "update-race"), UpdateCircleCommand{CircleID: created.CircleID, Name: &name})
	if err != nil || updated.Version != 2 || updated.IdempotentReplay {
		t.Fatalf("CAS retry drift: %+v err=%v", updated, err)
	}
}

func TestCircleArchiveNoopPersistsReceiptAndReplays(t *testing.T) {
	facade, store, _ := newFacadeUnderTest()
	created, err := facade.Create(commandContext("persona-owner", "create-noop"), CreateCircleCommand{Name: "归档圈"})
	if err != nil {
		t.Fatal(err)
	}
	archived, err := facade.Archive(commandContext("persona-owner", "archive-1"), created.CircleID)
	if err != nil || archived.Status != circlemodel.CircleStatusArchived || archived.Version != 2 {
		t.Fatalf("archive drift: %+v err=%v", archived, err)
	}

	noop, err := facade.Archive(commandContext("persona-owner", "archive-noop"), created.CircleID)
	if err != nil || !noop.IdempotentReplay || noop.Version != 2 {
		t.Fatalf("archive no-op must persist receipt without version bump: %+v err=%v", noop, err)
	}
	if store.outboxCount != 2 {
		t.Fatalf("no-op must not append outbox facts, got %d", store.outboxCount)
	}
	replay, err := facade.Archive(commandContext("persona-owner", "archive-noop"), created.CircleID)
	if err != nil || !replay.IdempotentReplay || replay.Version != 2 {
		t.Fatalf("archive no-op replay drift: %+v err=%v", replay, err)
	}
}

func TestCircleSectionsRejectInvalidConfiguration(t *testing.T) {
	facade, _, _ := newFacadeUnderTest()
	created, err := facade.Create(commandContext("persona-owner", "create-sections"), CreateCircleCommand{Name: "板块圈"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = facade.UpdateSections(commandContext("persona-owner", "sections-dup"), UpdateCircleSectionsCommand{
		CircleID: created.CircleID,
		Sections: []circlemodel.CircleSectionConfig{
			{SectionType: circlemodel.CircleSectionTypeChat, Visible: true, Order: 0},
			{SectionType: circlemodel.CircleSectionTypeChat, Visible: true, Order: 1},
		},
	})
	if !isCode(err, "CIRCLE.USER.invalid_argument") {
		t.Fatalf("duplicate sectionType must fail closed, got %v", err)
	}
}

func isCode(err error, code string) bool {
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		return false
	}
	return appErr.Code.String() == code
}

// --- 内存 store fake（契约与 Mongo 实现同型） ---

type memoryCircleAggregateStore struct {
	circles      map[string]circlemodel.Circle
	receipts     map[string]memoryCircleReceipt
	outboxCount  int
	conflictOnce bool
}

type memoryCircleReceipt struct {
	digest  string
	receipt circleports.CommitReceipt
}

func newMemoryCircleAggregateStore() *memoryCircleAggregateStore {
	return &memoryCircleAggregateStore{
		circles:  map[string]circlemodel.Circle{},
		receipts: map[string]memoryCircleReceipt{},
	}
}

func (store *memoryCircleAggregateStore) Load(_ context.Context, circleID string) (circlemodel.Circle, bool, error) {
	circle, found := store.circles[strings.TrimSpace(circleID)]
	return circle, found, nil
}

func (store *memoryCircleAggregateStore) Commit(_ context.Context, request circleports.CommitRequest) (circleports.CommitReceipt, error) {
	if entry, found := store.receipts[request.ReceiptKey]; found {
		if entry.digest != request.CommandDigest {
			return circleports.CommitReceipt{}, circlemodel.ErrIdempotencyConflict
		}
		receipt := entry.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	if store.conflictOnce {
		store.conflictOnce = false
		return circleports.CommitReceipt{}, circlemodel.ErrVersionConflict
	}
	var currentPointer *circlemodel.Circle
	if current, found := store.circles[request.Change.CircleID]; found {
		currentPointer = &current
	}
	next, err := circlemodel.Apply(currentPointer, request.Change)
	if err != nil {
		return circleports.CommitReceipt{}, err
	}
	store.circles[next.ID] = next
	store.outboxCount++
	receipt := circleports.CommitReceipt{CircleID: next.ID, Version: next.Version, Status: next.Status}
	store.receipts[request.ReceiptKey] = memoryCircleReceipt{digest: request.CommandDigest, receipt: receipt}
	return receipt, nil
}

func (store *memoryCircleAggregateStore) RecordNoopReceipt(_ context.Context, noop circleports.NoopReceipt) (circleports.CommitReceipt, error) {
	if entry, found := store.receipts[noop.ReceiptKey]; found {
		if entry.digest != noop.CommandDigest {
			return circleports.CommitReceipt{}, circlemodel.ErrIdempotencyConflict
		}
		receipt := entry.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	receipt := circleports.CommitReceipt{CircleID: noop.CircleID, Version: noop.Version, Status: noop.Status}
	store.receipts[noop.ReceiptKey] = memoryCircleReceipt{digest: noop.CommandDigest, receipt: receipt}
	return receipt, nil
}

type memoryRoleReader struct {
	roles map[string]string
}

func (reader *memoryRoleReader) ReadMembershipRole(_ context.Context, circleID, personaID string) (string, string, bool, error) {
	role, found := reader.roles[circleID+"/"+personaID]
	if !found {
		return "", "", false, nil
	}
	return role, "active", true, nil
}
