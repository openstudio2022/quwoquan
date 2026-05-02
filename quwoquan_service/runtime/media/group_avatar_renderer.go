package runtimemedia

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/color"
	"image/draw"
	_ "image/jpeg"
	"image/png"
	"io"
	"net/http"
	"strings"
	"time"
)

const groupAvatarCanvasSize = 256

// RenderGroupAvatarPNG 将最多 9 张成员头像合成为一张 PNG（2–9 宫格）。
// 下载失败或 URL 为空时使用占位图，保证始终产出非空 PNG。
func RenderGroupAvatarPNG(ctx context.Context, client *http.Client, avatarURLs []string, canvas int) ([]byte, error) {
	if canvas <= 0 {
		canvas = groupAvatarCanvasSize
	}
	if client == nil {
		client = http.DefaultClient
	}
	n := len(avatarURLs)
	if n == 0 {
		return nil, fmt.Errorf("group avatar render requires at least one avatar url")
	}
	if n > 9 {
		avatarURLs = avatarURLs[:9]
		n = 9
	}
	if n < 2 {
		avatarURLs = append(append([]string{}, avatarURLs...), "")
		n = 2
	}

	cols := int(ceilSqrt(n))
	rows := (n + cols - 1) / cols
	cellW := canvas / cols
	cellH := canvas / rows
	if cellW <= 0 || cellH <= 0 {
		return nil, fmt.Errorf("invalid canvas size %d", canvas)
	}

	dst := image.NewRGBA(image.Rect(0, 0, canvas, canvas))
	draw.Draw(dst, dst.Bounds(), &image.Uniform{color.RGBA{0xe8, 0xe8, 0xec, 0xff}}, image.Point{}, draw.Src)

	for idx := 0; idx < n; idx++ {
		row := idx / cols
		col := idx % cols
		x0 := col * cellW
		y0 := row * cellH
		cell := image.Rect(x0, y0, x0+cellW, y0+cellH)

		var tile image.Image
		url := ""
		if idx < len(avatarURLs) {
			url = strings.TrimSpace(avatarURLs[idx])
		}
		if url != "" {
			if img, err := fetchAvatarImage(ctx, client, url); err == nil && img != nil {
				tile = centerCropSquare(img, cell.Dx(), cell.Dy())
			}
		}
		if tile == nil {
			tile = placeholderTile(cell.Dx(), cell.Dy(), idx)
		}
		draw.Draw(dst, cell, tile, image.Point{}, draw.Over)
	}

	var buf bytes.Buffer
	if err := png.Encode(&buf, dst); err != nil {
		return nil, fmt.Errorf("encode group avatar png: %w", err)
	}
	return buf.Bytes(), nil
}

func ceilSqrt(n int) int {
	if n <= 1 {
		return 1
	}
	i := 1
	for i*i < n {
		i++
	}
	return i
}

func fetchAvatarImage(ctx context.Context, client *http.Client, rawURL string) (image.Image, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("avatar fetch status %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, err
	}
	img, _, err := image.Decode(bytes.NewReader(body))
	if err != nil || img == nil {
		return nil, fmt.Errorf("decode avatar: %w", err)
	}
	return img, nil
}

func centerCropSquare(src image.Image, outW, outH int) image.Image {
	if outW <= 0 || outH <= 0 {
		return placeholderTile(1, 1, 0)
	}
	b := src.Bounds()
	sw := b.Dx()
	sh := b.Dy()
	if sw <= 0 || sh <= 0 {
		return placeholderTile(outW, outH, 0)
	}
	side := sw
	if sh < sw {
		side = sh
	}
	x0 := b.Min.X + (sw-side)/2
	y0 := b.Min.Y + (sh-side)/2

	cropped := image.NewRGBA(image.Rect(0, 0, side, side))
	for y := 0; y < side; y++ {
		for x := 0; x < side; x++ {
			cropped.Set(x, y, src.At(x0+x, y0+y))
		}
	}
	dst := image.NewRGBA(image.Rect(0, 0, outW, outH))
	scaleNearest(cropped, dst)
	return dst
}

func scaleNearest(src image.Image, dst *image.RGBA) {
	sb := src.Bounds()
	db := dst.Bounds()
	sw := sb.Dx()
	sh := sb.Dy()
	dw := db.Dx()
	dh := db.Dy()
	if sw <= 0 || sh <= 0 || dw <= 0 || dh <= 0 {
		return
	}
	for y := 0; y < dh; y++ {
		sy := sb.Min.Y + y*sh/dh
		for x := 0; x < dw; x++ {
			sx := sb.Min.X + x*sw/dw
			dst.Set(db.Min.X+x, db.Min.Y+y, src.At(sx, sy))
		}
	}
}

func placeholderTile(w, h int, seed int) image.Image {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	base := color.RGBA{
		R: uint8(160 + (seed*17)%80),
		G: uint8(170 + (seed*31)%60),
		B: uint8(180 + (seed*13)%50),
		A: 255,
	}
	draw.Draw(img, img.Bounds(), &image.Uniform{base}, image.Point{}, draw.Src)
	return img
}

// DefaultGroupAvatarHTTPClient 用于下载成员头像，短超时避免阻塞重算 worker。
func DefaultGroupAvatarHTTPClient() *http.Client {
	return &http.Client{Timeout: 8 * time.Second}
}
