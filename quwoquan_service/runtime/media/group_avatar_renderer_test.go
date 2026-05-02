package runtimemedia

import (
	"bytes"
	"context"
	"image/png"
	"testing"
)

func TestRenderGroupAvatarPNG_DeterministicPlaceholder(t *testing.T) {
	ctx := context.Background()
	pngBytes, err := RenderGroupAvatarPNG(ctx, nil, []string{"", ""}, 64)
	if err != nil {
		t.Fatal(err)
	}
	img, err := png.Decode(bytes.NewReader(pngBytes))
	if err != nil {
		t.Fatal(err)
	}
	if img.Bounds().Dx() != 64 || img.Bounds().Dy() != 64 {
		t.Fatalf("unexpected bounds %v", img.Bounds())
	}
}
