package behavior

import (
	"context"
	"errors"
	"testing"
)

type recordingWishlistStateReader struct {
	userID     string
	objectID   string
	objectKind string
	wishlisted bool
	err        error
}

func (r *recordingWishlistStateReader) IsWishlisted(
	_ context.Context,
	userID string,
	objectID string,
	objectKind string,
) (bool, error) {
	r.userID = userID
	r.objectID = objectID
	r.objectKind = objectKind
	return r.wishlisted, r.err
}

func TestGetEntityWishlistStateReturnsReaderState(t *testing.T) {
	reader := &recordingWishlistStateReader{wishlisted: true}
	service := NewBehaviorService(
		nil,
		nil,
		WithWishlistStateReader(reader),
	)

	state, err := service.GetEntityWishlistState(
		context.Background(),
		"user-1",
		"homepage-1",
		"homepage",
	)
	if err != nil {
		t.Fatalf("GetEntityWishlistState() error = %v", err)
	}
	if !state.Wishlisted ||
		state.ObjectID != "homepage-1" ||
		state.ObjectKind != "homepage" {
		t.Fatalf("unexpected state: %+v", state)
	}
	if reader.userID != "user-1" ||
		reader.objectID != "homepage-1" ||
		reader.objectKind != "homepage" {
		t.Fatalf("reader received wrong identity: %+v", reader)
	}
}

func TestGetEntityWishlistStateRejectsMissingObjectIdentity(t *testing.T) {
	service := NewBehaviorService(
		nil,
		nil,
		WithWishlistStateReader(&recordingWishlistStateReader{}),
	)

	if _, err := service.GetEntityWishlistState(
		context.Background(),
		"user-1",
		"",
		"homepage",
	); err == nil {
		t.Fatal("expected invalid object identity error")
	}
}

func TestGetEntityWishlistStatePropagatesReaderFailure(t *testing.T) {
	expected := errors.New("read failed")
	service := NewBehaviorService(
		nil,
		nil,
		WithWishlistStateReader(&recordingWishlistStateReader{err: expected}),
	)

	if _, err := service.GetEntityWishlistState(
		context.Background(),
		"user-1",
		"homepage-1",
		"homepage",
	); !errors.Is(err, expected) {
		t.Fatalf("error = %v, want %v", err, expected)
	}
}
