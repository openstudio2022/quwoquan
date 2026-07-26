package accountclosure_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/accountclosure"
	"testing"
)

type persistentSubjectLookupStub struct {
	closed bool
	reads  int
}

func (stub *persistentSubjectLookupStub) IsSubjectClosed(
	context.Context,
	string,
) (bool, error) {
	stub.reads++
	return stub.closed, nil
}

type subjectStateCacheStub struct {
	closed       bool
	knownOpen    bool
	blocked      []string
	openRemember int
}

func (stub *subjectStateCacheStub) IsSubjectClosed(
	context.Context,
	string,
) (bool, error) {
	return stub.closed, nil
}

func (stub *subjectStateCacheStub) IsSubjectKnownOpen(
	context.Context,
	string,
) (bool, error) {
	return stub.knownOpen, nil
}

func (stub *subjectStateCacheStub) RememberOpenSubject(
	context.Context,
	string,
) error {
	stub.openRemember++
	return nil
}

func (stub *subjectStateCacheStub) BlockClosedSubjects(
	_ context.Context,
	subjectIDs []string,
) error {
	stub.blocked = append(stub.blocked, subjectIDs...)
	return nil
}

func TestSubjectClosureGuardRestoresDurableTombstoneIntoCache(t *testing.T) {
	persistent := &persistentSubjectLookupStub{closed: true}
	cache := &subjectStateCacheStub{}
	guard, err := NewSubjectClosureGuard(persistent, cache)
	if err != nil {
		t.Fatal(err)
	}

	closed, err := guard.IsSubjectClosed(context.Background(), "user-1")
	if err != nil {
		t.Fatal(err)
	}
	if !closed {
		t.Fatal("durable tombstone must close the subject")
	}
	if persistent.reads != 1 {
		t.Fatalf("expected one durable lookup, got %d", persistent.reads)
	}
	if len(cache.blocked) != 1 || cache.blocked[0] != "user-1" {
		t.Fatalf("durable tombstone was not restored to cache: %v", cache.blocked)
	}
	if cache.openRemember != 0 {
		t.Fatal("closed subject must never be cached as open")
	}
}

func TestSubjectClosureGuardCachesDurableOpenMiss(t *testing.T) {
	persistent := &persistentSubjectLookupStub{}
	cache := &subjectStateCacheStub{}
	guard, err := NewSubjectClosureGuard(persistent, cache)
	if err != nil {
		t.Fatal(err)
	}

	closed, err := guard.IsSubjectClosed(context.Background(), "user-1")
	if err != nil {
		t.Fatal(err)
	}
	if closed {
		t.Fatal("open subject was incorrectly closed")
	}
	if persistent.reads != 1 || cache.openRemember != 1 {
		t.Fatalf(
			"expected one durable miss and one open cache write, reads=%d writes=%d",
			persistent.reads,
			cache.openRemember,
		)
	}

	cache.knownOpen = true
	closed, err = guard.IsSubjectClosed(context.Background(), "user-1")
	if err != nil || closed {
		t.Fatalf("cached open subject result = %v, %v", closed, err)
	}
	if persistent.reads != 1 {
		t.Fatalf("known-open cache must bypass Mongo, reads=%d", persistent.reads)
	}
}
