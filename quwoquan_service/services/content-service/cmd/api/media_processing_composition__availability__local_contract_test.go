package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMediaProcessingConfigIsSharedAcrossFourEnvironments(t *testing.T) {
	serviceRoot, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatalf("resolve content-service root: %v", err)
	}
	originalWorkingDirectory, err := os.Getwd()
	if err != nil {
		t.Fatalf("read working directory: %v", err)
	}
	if err := os.Chdir(serviceRoot); err != nil {
		t.Fatalf("enter content-service root: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(originalWorkingDirectory) })

	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			cfg, err := loadRuntimeConfig("content-service", environment, "", "")
			if err != nil {
				t.Fatalf("load %s config: %v", environment, err)
			}
			if cfg.MediaProcessing.FFmpegPath != "ffmpeg" ||
				cfg.MediaProcessing.FFprobePath != "ffprobe" ||
				cfg.MediaProcessing.IntervalMs != 2_000 ||
				cfg.MediaProcessing.JobTimeoutMs != 900_000 {
				t.Fatalf(
					"%s media processing must inherit the shared default: %+v",
					environment,
					cfg.MediaProcessing,
				)
			}
		})
	}
}
