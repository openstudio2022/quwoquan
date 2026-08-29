package servicekit

import (
	"errors"
	"testing"

	"quwoquan_service/runtime/servicehost"
)

func TestRunStandalonePropagatesModuleConstructionFailure(t *testing.T) {
	expected := errors.New("bootstrap failed")
	err := runStandalone(func() (servicehost.Module, error) {
		return nil, expected
	})
	if !errors.Is(err, expected) {
		t.Fatalf("expected bootstrap failure to propagate, got %v", err)
	}
}

func TestRunStandaloneRejectsNilModule(t *testing.T) {
	if err := runStandalone(func() (servicehost.Module, error) {
		return nil, nil
	}); err == nil {
		t.Fatal("expected supervisor to reject a nil module")
	}
}
