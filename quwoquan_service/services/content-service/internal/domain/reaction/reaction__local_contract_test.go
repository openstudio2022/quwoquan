package reaction

import (
	"testing"
	"time"
)

func TestContentReaction_IdentitySeparatesPersonaAndDevice(t *testing.T) {
	t.Parallel()

	persona, err := NewActor(ActorDimensionPersona, "same-id")
	if err != nil {
		t.Fatalf("persona actor: %v", err)
	}
	device, err := NewActor(ActorDimensionDevice, "same-id")
	if err != nil {
		t.Fatalf("device actor: %v", err)
	}
	personaIdentity, err := NewPostIdentity("post-1", persona)
	if err != nil {
		t.Fatalf("persona identity: %v", err)
	}
	deviceIdentity, err := NewPostIdentity("post-1", device)
	if err != nil {
		t.Fatalf("device identity: %v", err)
	}
	if personaIdentity.AggregateID() == deviceIdentity.AggregateID() {
		t.Fatal("persona and device dimensions must not collide")
	}
}

func TestContentReaction_PostAndCommentValuesPreserveIdentityAndVersion(t *testing.T) {
	t.Parallel()

	actor, err := NewActor(ActorDimensionPersona, "persona-1")
	if err != nil {
		t.Fatalf("actor: %v", err)
	}
	identity, err := NewPostIdentity("post-1", actor)
	if err != nil {
		t.Fatalf("identity: %v", err)
	}
	now := time.Now().UTC()
	aggregate, err := New(identity, ValueNone, now)
	if err != nil {
		t.Fatalf("new removed relation: %v", err)
	}
	if aggregate.Version() != 1 || aggregate.IsLiked() {
		t.Fatalf("unexpected initial relation: %+v", aggregate.Snapshot())
	}
	changed, err := aggregate.Set(ValueLike, now.Add(time.Second))
	if err != nil || !changed || aggregate.Version() != 2 || !aggregate.IsLiked() {
		t.Fatalf("like transition invalid: changed=%v version=%d err=%v", changed, aggregate.Version(), err)
	}
	changed, err = aggregate.Set(ValueNone, now.Add(2*time.Second))
	if err != nil || !changed || aggregate.Version() != 3 || aggregate.IsLiked() {
		t.Fatalf("unlike transition invalid: changed=%v version=%d err=%v", changed, aggregate.Version(), err)
	}
	if aggregate.Snapshot().ReactedAt != nil {
		t.Fatal("none relation must not retain reactedAt")
	}
	commentIdentity, err := NewCommentIdentity("comment-1", actor)
	if err != nil {
		t.Fatal(err)
	}
	commentReaction, err := New(commentIdentity, ValueDislike, now)
	if err != nil || commentReaction.Value() != ValueDislike {
		t.Fatalf("comment dislike: value=%q err=%v", commentReaction.Value(), err)
	}
	if _, err := aggregate.Set(ValueDislike, now.Add(3*time.Second)); err == nil {
		t.Fatal("Post target must reject dislike")
	}
}
