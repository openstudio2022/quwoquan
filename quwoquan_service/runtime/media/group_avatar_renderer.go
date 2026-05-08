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

// RenderGroupAvatarPNG 将最多 9 张成员头像合成为一张 PNG（1–9 宫格）。
// 下载失败或 URL 为空时使用占位图，保证始终产出非空 PNG。
func RenderGroupAvatarPNG(ctx context.Context, client *http.Client, avatarURLs []string, canvas int) ([]byte, error) {
	if client == nil {
		client = http.DefaultClient
	}
	images := make([]image.Image, 0, min(len(avatarURLs), 9))
	for idx := 0; idx < len(avatarURLs) && idx < 9; idx++ {
		url := strings.TrimSpace(avatarURLs[idx])
		var img image.Image
		if url != "" {
			if fetched, err := fetchAvatarImage(ctx, client, url); err == nil && fetched != nil {
				img = fetched
			}
		}
		images = append(images, img)
	}
	return RenderGroupAvatarImagesPNG(images, canvas)
}

// RenderGroupAvatarImagesPNG 使用与运行时完全相同的布局规则，将最多 9 张成员头像合成为 PNG。
// 传入 nil image 时会按对应位置回退为占位块，供离线 fixture 生成与运行时复用同一几何真相源。
func RenderGroupAvatarImagesPNG(images []image.Image, canvas int) ([]byte, error) {
	if canvas <= 0 {
		canvas = groupAvatarCanvasSize
	}
	n := len(images)
	if n == 0 {
		return nil, fmt.Errorf("group avatar render requires at least one image")
	}
	if n > 9 {
		images = images[:9]
		n = 9
	}

	frames, err := avatarGridFrames(canvas, n)
	if err != nil {
		return nil, err
	}
	if len(frames) != n {
		return nil, fmt.Errorf("group avatar frame count mismatch: %d != %d", len(frames), n)
	}
	if len(frames) == 0 {
		return nil, fmt.Errorf("invalid canvas size %d", canvas)
	}

	dst := image.NewRGBA(image.Rect(0, 0, canvas, canvas))
	draw.Draw(dst, dst.Bounds(), &image.Uniform{color.RGBA{0xe8, 0xe8, 0xec, 0xff}}, image.Point{}, draw.Src)

	for idx := 0; idx < n; idx++ {
		cell := frames[idx]
		var tile image.Image
		if images[idx] != nil {
			tile = centerCropSquare(images[idx], cell.Dx(), cell.Dy())
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

func avatarGridRows(n int) []int {
	switch {
	case n <= 0:
		return nil
	case n == 1:
		return []int{1}
	case n == 2:
		return []int{2}
	case n == 3:
		return []int{1, 2}
	case n == 4:
		return []int{2, 2}
	case n == 5:
		return []int{2, 3}
	case n == 6:
		return []int{3, 3}
	case n == 7:
		return []int{1, 3, 3}
	case n == 8:
		return []int{2, 3, 3}
	default:
		return []int{3, 3, 3}
	}
}

func avatarGridFrames(canvas int, n int) ([]image.Rectangle, error) {
	rows := avatarGridRows(n)
	if len(rows) == 0 {
		return nil, fmt.Errorf("group avatar requires at least one tile")
	}
	if n == 1 {
		return []image.Rectangle{image.Rect(0, 0, canvas, canvas)}, nil
	}
	maxCols := 1
	for _, row := range rows {
		if row > maxCols {
			maxCols = row
		}
	}
	padding := canvas / 20
	gap := canvas / 64
	if gap < 2 {
		gap = 2
	}
	inner := canvas - padding*2
	cellSize := inner
	if maxCols > 1 {
		cellSize = (inner - gap*(maxCols-1)) / maxCols
	}
	if cellSize <= 0 {
		return nil, fmt.Errorf("invalid group avatar geometry canvas=%d n=%d", canvas, n)
	}
	totalHeight := len(rows)*cellSize + (len(rows)-1)*gap
	originY := (canvas - totalHeight) / 2
	frames := make([]image.Rectangle, 0, n)
	for rowIndex, cols := range rows {
		rowWidth := cols * cellSize
		if cols > 1 {
			rowWidth += (cols - 1) * gap
		}
		originX := (canvas - rowWidth) / 2
		y := originY + rowIndex*(cellSize+gap)
		for col := 0; col < cols; col++ {
			x := originX + col*(cellSize+gap)
			frames = append(frames, image.Rect(x, y, x+cellSize, y+cellSize))
		}
	}
	return frames, nil
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
