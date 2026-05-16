package main

import (
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"log"
	"os"
	"path/filepath"

	runtimemedia "quwoquan_service/runtime/media"
)

func main() {
	if len(os.Args) < 3 {
		log.Fatalf("usage: go run ./cmd/render-group-avatar <output-path> <input-image> [<input-image>...]")
	}
	outputPath := os.Args[1]
	inputPaths := os.Args[2:]
	images := make([]image.Image, 0, len(inputPaths))
	for _, inputPath := range inputPaths {
		img, err := loadImage(inputPath)
		if err != nil {
			log.Fatalf("load image %s: %v", inputPath, err)
		}
		images = append(images, img)
	}
	raw, err := runtimemedia.RenderGroupAvatarImagesPNG(images, 256)
	if err != nil {
		log.Fatalf("render group avatar: %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		log.Fatalf("mkdir output dir: %v", err)
	}
	if err := os.WriteFile(outputPath, raw, 0o644); err != nil {
		log.Fatalf("write output %s: %v", outputPath, err)
	}
}

func loadImage(path string) (image.Image, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	img, _, err := image.Decode(file)
	if err != nil {
		return nil, fmt.Errorf("decode image: %w", err)
	}
	return img, nil
}
