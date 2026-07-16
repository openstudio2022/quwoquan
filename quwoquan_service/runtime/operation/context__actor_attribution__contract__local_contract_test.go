package operation

import (
	"context"
	"testing"
)

func TestActorContextDoesNotUseAccountAsBusinessActor(t *testing.T) {
	actor := ActorContext{AccountID: "account-1"}
	if _, ok := actor.BusinessActorID(); ok {
		t.Fatal("accountId must not be exposed as a business actor")
	}
	if err := actor.Validate(ActorPersona); err == nil {
		t.Fatal("persona requirement must reject account-only context")
	}
}

func TestOperationContextPropagatesTypedAttribution(t *testing.T) {
	want := Context{
		OperationID: "content.post.GetPost",
		RequestID:   "request-1",
		TraceID:     "trace-1",
		SurfaceID:   "postDetail",
		Actor: ActorContext{
			AccountID: "account-1",
			PersonaID: "persona-1",
		},
		Attributes: map[string]string{"environment": "gamma"},
	}
	if err := want.Validate(ActorPersona); err != nil {
		t.Fatalf("validate operation context: %v", err)
	}

	ctx := WithContext(context.Background(), want)
	got, ok := FromContext(ctx)
	if !ok {
		t.Fatal("operation context missing")
	}
	if got.OperationID != want.OperationID || got.Actor.PersonaID != want.Actor.PersonaID {
		t.Fatalf("unexpected propagated context: %+v", got)
	}
}
