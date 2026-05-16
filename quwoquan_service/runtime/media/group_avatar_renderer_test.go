package runtimemedia

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAvatarGridRowsMatchSpec(t *testing.T) {
	cases := map[int][]int{
		1: {1},
		2: {2},
		3: {1, 2},
		4: {2, 2},
		5: {2, 3},
		6: {3, 3},
		7: {1, 3, 3},
		8: {2, 3, 3},
		9: {3, 3, 3},
	}
	for count, want := range cases {
		got := avatarGridRows(count)
		if len(got) != len(want) {
			t.Fatalf("count=%d rows len mismatch got=%v want=%v", count, got, want)
		}
		for idx := range want {
			if got[idx] != want[idx] {
				t.Fatalf("count=%d row[%d] mismatch got=%v want=%v", count, idx, got, want)
			}
		}
	}
}

func TestRenderGroupAvatarPNG_SingleMemberUsesFullCanvas(t *testing.T) {
	server := newSolidAvatarServer()
	defer server.Close()

	ctx := context.Background()
	pngBytes, err := RenderGroupAvatarPNG(ctx, server.Client(), []string{
		server.URL + "/red",
	}, 96)
	if err != nil {
		t.Fatal(err)
	}
	img := decodePNG(t, pngBytes)
	if img.Bounds().Dx() != 96 || img.Bounds().Dy() != 96 {
		t.Fatalf("unexpected bounds %v", img.Bounds())
	}
	assertPixelColor(t, img, 4, 4, color.RGBA{0xff, 0x00, 0x00, 0xff})
	assertPixelColor(t, img, 48, 48, color.RGBA{0xff, 0x00, 0x00, 0xff})
}

func TestRenderGroupAvatarPNG_ThreeMembersUseOneTwoLayout(t *testing.T) {
	server := newSolidAvatarServer()
	defer server.Close()

	ctx := context.Background()
	pngBytes, err := RenderGroupAvatarPNG(ctx, server.Client(), []string{
		server.URL + "/red",
		server.URL + "/green",
		server.URL + "/blue",
	}, 96)
	if err != nil {
		t.Fatal(err)
	}
	img := decodePNG(t, pngBytes)
	assertPixelColor(t, img, 47, 25, color.RGBA{0xff, 0x00, 0x00, 0xff})
	assertPixelColor(t, img, 25, 69, color.RGBA{0x00, 0xff, 0x00, 0xff})
	assertPixelColor(t, img, 69, 69, color.RGBA{0x00, 0x00, 0xff, 0xff})
	assertPixelColor(t, img, 0, 0, color.RGBA{0xe8, 0xe8, 0xec, 0xff})
}

func newSolidAvatarServer() *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		img := image.NewRGBA(image.Rect(0, 0, 32, 32))
		fill := color.RGBA{0x88, 0x88, 0x88, 0xff}
		switch r.URL.Path {
		case "/red":
			fill = color.RGBA{0xff, 0x00, 0x00, 0xff}
		case "/green":
			fill = color.RGBA{0x00, 0xff, 0x00, 0xff}
		case "/blue":
			fill = color.RGBA{0x00, 0x00, 0xff, 0xff}
		}
		for y := 0; y < 32; y++ {
			for x := 0; x < 32; x++ {
				img.Set(x, y, fill)
			}
		}
		_ = png.Encode(w, img)
	}))
}

func decodePNG(t *testing.T, raw []byte) image.Image {
	t.Helper()
	img, err := png.Decode(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	return img
}

func assertPixelColor(t *testing.T, img image.Image, x int, y int, want color.RGBA) {
	t.Helper()
	got := color.RGBAModel.Convert(img.At(x, y)).(color.RGBA)
	if got != want {
		t.Fatalf("pixel(%d,%d) mismatch got=%v want=%v", x, y, got, want)
	}
}
