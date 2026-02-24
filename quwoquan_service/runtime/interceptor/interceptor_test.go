package interceptor

import (
	"context"
	"log/slog"
	"os"
	"testing"

	"quwoquan_service/runtime/registry"
)

func TestChain_ExecuteOrder(t *testing.T) {
	var order []string

	a := &testInterceptor{name: "A", fn: func(ctx context.Context, ic *Context, next Handler) error {
		order = append(order, "A-before")
		err := next(ctx, ic)
		order = append(order, "A-after")
		return err
	}}
	b := &testInterceptor{name: "B", fn: func(ctx context.Context, ic *Context, next Handler) error {
		order = append(order, "B-before")
		err := next(ctx, ic)
		order = append(order, "B-after")
		return err
	}}

	chain := NewChain(a, b)
	ic := &Context{EntityName: "Test", Operation: OpRead}

	err := chain.Execute(context.Background(), ic, func(ctx context.Context, _ *Context) error {
		order = append(order, "final")
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	expected := []string{"A-before", "B-before", "final", "B-after", "A-after"}
	if len(order) != len(expected) {
		t.Fatalf("order length: got %d, want %d", len(order), len(expected))
	}
	for i, v := range expected {
		if order[i] != v {
			t.Errorf("order[%d]: got %q, want %q", i, order[i], v)
		}
	}
}

func TestAPIExposureInterceptor_FiltersDrop(t *testing.T) {
	api := NewAPIExposureInterceptor()
	chain := NewChain(api)

	data := map[string]any{
		"userId": "123",
		"phone":  "13800001111",
		"bio":    "hello",
	}
	ic := &Context{
		EntityName: "UserProfile",
		Operation:  OpRead,
		Input:      &data,
		FieldMeta: []registry.FieldDef{
			{Name: "userId", APIExposure: "read"},
			{Name: "phone", APIExposure: "drop"},
			{Name: "bio", APIExposure: "read"},
		},
	}

	err := chain.Execute(context.Background(), ic, func(ctx context.Context, _ *Context) error {
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	if _, ok := data["phone"]; ok {
		t.Error("phone should be dropped from read output")
	}
	if data["userId"] != "123" {
		t.Error("userId should remain")
	}
}

func TestAPIExposureInterceptor_FiltersReadOnly(t *testing.T) {
	api := NewAPIExposureInterceptor()
	chain := NewChain(api)

	data := map[string]any{
		"userId":    "123",
		"createdAt": "2024-01-01",
		"bio":       "new bio",
	}
	ic := &Context{
		EntityName: "UserProfile",
		Operation:  OpUpdate,
		Input:      &data,
		FieldMeta: []registry.FieldDef{
			{Name: "userId", APIExposure: "read"},
			{Name: "createdAt", APIExposure: "read"},
			{Name: "bio", APIExposure: "read_write"},
		},
	}

	err := chain.Execute(context.Background(), ic, func(ctx context.Context, _ *Context) error {
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	if _, ok := data["userId"]; ok {
		t.Error("userId should be filtered from write input")
	}
	if _, ok := data["createdAt"]; ok {
		t.Error("createdAt should be filtered from write input")
	}
	if data["bio"] != "new bio" {
		t.Error("bio should remain writable")
	}
}

func TestLogMaskingInterceptor(t *testing.T) {
	masker := NewLogMaskingInterceptor()
	chain := NewChain(masker)

	data := map[string]any{
		"userId": "123",
		"phone":  "13800001111",
		"bio":    "hello world",
	}
	ic := &Context{
		EntityName: "UserProfile",
		Operation:  OpRead,
		Input:      &data,
		FieldMeta: []registry.FieldDef{
			{Name: "userId", LogPolicy: "allow"},
			{Name: "phone", LogPolicy: "mask"},
			{Name: "bio", LogPolicy: "allow"},
		},
	}

	err := chain.Execute(context.Background(), ic, func(ctx context.Context, _ *Context) error {
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	phone, ok := data["phone"].(string)
	if !ok || phone == "13800001111" {
		t.Errorf("phone should be masked, got %v", data["phone"])
	}
	if phone != "1*********1" {
		t.Errorf("phone mask: got %q, want %q", phone, "1*********1")
	}
}

func TestAuditInterceptor_WritesLog(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelDebug}))
	audit := NewAuditInterceptor(logger)
	chain := NewChain(audit)

	ic := &Context{
		EntityName: "Post",
		Operation:  OpCreate,
		EntityID:   "post-123",
	}

	err := chain.Execute(context.Background(), ic, func(ctx context.Context, _ *Context) error {
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

type testInterceptor struct {
	name string
	fn   func(ctx context.Context, ic *Context, next Handler) error
}

func (t *testInterceptor) Name() string { return t.name }
func (t *testInterceptor) Intercept(ctx context.Context, ic *Context, next Handler) error {
	return t.fn(ctx, ic, next)
}
