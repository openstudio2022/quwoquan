// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: list-circle-files-local
// readiness_case: create-circle-file-local
// readiness_case: get-circle-file-local
// readiness_case: update-circle-file-local
// readiness_case: delete-circle-file-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	fileapp "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	filemodel "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	fileports "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/ports"
)

func TestCircleFileFacadesOwnCommandAndQueryLifecycle(t *testing.T) {
	store := newFileContractStore()
	commands := fileapp.NewCommandFacade(store, store, store)
	queries := fileapp.NewQueryFacade(store, store)

	created, err := commands.Create(
		fileContractContext("CreateCircleFile", "create-folder"),
		fileapp.CreateCommand{
			CircleID: "circle-1", Name: "行程资料", FileType: filemodel.CircleFileTypeFolder,
		},
	)
	if err != nil || created.FileID == "" || created.Version != 1 || created.Status != "active" {
		t.Fatalf("create result=%+v err=%v", created, err)
	}
	listed, err := queries.List(
		fileContractContext("ListCircleFiles", "list-files"),
		fileports.ListQuery{CircleID: "circle-1", Limit: 20},
	)
	if err != nil || len(listed.Items) != 1 || listed.Items[0].FileID != created.FileID {
		t.Fatalf("list result=%+v err=%v", listed, err)
	}
	got, err := queries.Get(
		fileContractContext("GetCircleFile", "get-file"), "circle-1", created.FileID,
	)
	if err != nil || got.FileID != created.FileID || got.Name != "行程资料" {
		t.Fatalf("get result=%+v err=%v", got, err)
	}

	updatedName := "行程资料库"
	updated, err := commands.Update(
		fileContractContext("UpdateCircleFile", "update-folder"),
		fileapp.UpdateCommand{
			CircleID: "circle-1", FileID: created.FileID,
			ExpectedVersion: created.Version, Name: &updatedName,
		},
	)
	if err != nil || updated.Version != 2 || store.file == nil || store.file.Name != updatedName {
		t.Fatalf("update result=%+v file=%+v err=%v", updated, store.file, err)
	}
	deleted, err := commands.Delete(
		fileContractContext("DeleteCircleFile", "delete-folder"),
		fileapp.DeleteCommand{CircleID: "circle-1", FileID: created.FileID},
	)
	if err != nil || deleted.Version != 3 || deleted.Status != "deleted" ||
		store.file.Status != filemodel.CircleFileStatusDeleted {
		t.Fatalf("delete result=%+v file=%+v err=%v", deleted, store.file, err)
	}
}

func fileContractContext(operationID, idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "circle.circle_file." + operationID,
		RequestID:      "request-" + idempotencyKey,
		TraceID:        "trace-" + idempotencyKey,
		IdempotencyKey: idempotencyKey,
		Actor: operation.ActorContext{
			AccountID: "account-1", PersonaID: "persona-1",
		},
	})
}

type fileReceipt struct {
	digest string
	value  fileports.CommitReceipt
}

type fileContractStore struct {
	file     *filemodel.CircleFile
	receipts map[string]fileReceipt
}

func newFileContractStore() *fileContractStore {
	return &fileContractStore{receipts: make(map[string]fileReceipt)}
}

func (store *fileContractStore) Load(
	_ context.Context, fileID string,
) (filemodel.CircleFile, bool, error) {
	if store.file == nil || store.file.ID != fileID {
		return filemodel.CircleFile{}, false, nil
	}
	return *store.file, true, nil
}

func (store *fileContractStore) Commit(
	_ context.Context, request fileports.CommitRequest,
) (fileports.CommitReceipt, error) {
	if existing, found := store.receipts[request.ReceiptKey]; found {
		if existing.digest != request.CommandDigest {
			return fileports.CommitReceipt{}, filemodel.ErrIdempotencyConflict
		}
		result := existing.value
		result.Replayed = true
		return result, nil
	}
	next, err := filemodel.Apply(store.file, request.Change)
	if err != nil {
		return fileports.CommitReceipt{}, err
	}
	store.file = &next
	result := fileports.CommitReceipt{
		FileID: next.ID, Version: next.Version, Status: next.Status,
	}
	store.receipts[request.ReceiptKey] = fileReceipt{digest: request.CommandDigest, value: result}
	return result, nil
}

func (store *fileContractStore) RecordNoopReceipt(
	_ context.Context, request fileports.NoopReceipt,
) (fileports.CommitReceipt, error) {
	if existing, found := store.receipts[request.ReceiptKey]; found {
		if existing.digest != request.CommandDigest {
			return fileports.CommitReceipt{}, filemodel.ErrIdempotencyConflict
		}
		result := existing.value
		result.Replayed = true
		return result, nil
	}
	result := fileports.CommitReceipt{
		FileID: request.FileID, Version: request.Version, Status: request.Status,
	}
	store.receipts[request.ReceiptKey] = fileReceipt{digest: request.CommandDigest, value: result}
	return result, nil
}

func (*fileContractStore) ReadCircleStoragePolicy(
	context.Context, string,
) (fileports.CircleStoragePolicySlice, bool, error) {
	return fileports.CircleStoragePolicySlice{
		CircleID: "circle-1", State: "active", QuotaBytes: 1 << 20,
	}, true, nil
}

func (*fileContractStore) ReadCircleMembership(
	context.Context, string, string,
) (fileports.MembershipPolicySlice, bool, error) {
	return fileports.MembershipPolicySlice{
		PersonaID: "persona-1", Role: "owner", State: "active",
	}, true, nil
}

func (*fileContractStore) ReadGroupMembership(
	context.Context, string, string,
) (fileports.MembershipPolicySlice, bool, error) {
	return fileports.MembershipPolicySlice{}, false, nil
}

func (store *fileContractStore) ReadParentFolder(
	_ context.Context, circleID string, fileID string,
) (filemodel.CircleFile, bool, error) {
	if store.file == nil || store.file.CircleID != circleID || store.file.ID != fileID {
		return filemodel.CircleFile{}, false, nil
	}
	return *store.file, true, nil
}

func (*fileContractStore) ParentChainContains(
	context.Context, string, string, string,
) (bool, error) {
	return false, nil
}

func (*fileContractStore) ReadOwnedReadyAsset(
	context.Context, string, string,
) (fileports.MediaAssetOwnerSlice, bool, error) {
	return fileports.MediaAssetOwnerSlice{}, false, nil
}

func (store *fileContractStore) ReadFile(
	_ context.Context, circleID string, fileID string,
) (filemodel.CircleFile, bool, error) {
	if store.file == nil || store.file.CircleID != circleID || store.file.ID != fileID {
		return filemodel.CircleFile{}, false, nil
	}
	return *store.file, true, nil
}

func (store *fileContractStore) ListFiles(
	_ context.Context, query fileports.ListQuery,
) (fileports.PageSlice, error) {
	page := fileports.PageSlice{Items: []filemodel.CircleFile{}}
	if store.file != nil && store.file.CircleID == query.CircleID &&
		store.file.Status == filemodel.CircleFileStatusActive {
		page.Items = append(page.Items, *store.file)
	}
	return page, nil
}
