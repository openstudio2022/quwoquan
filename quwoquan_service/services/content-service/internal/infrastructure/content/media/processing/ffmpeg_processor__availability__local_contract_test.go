package processing

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	mediaprocessing "quwoquan_service/services/content-service/internal/application/media/processing"
)

func TestFFmpegMediaProcessorFailsFastWhenRuntimeBinaryIsMissing(t *testing.T) {
	tempDir := t.TempDir()
	availableBinary := filepath.Join(tempDir, "available")
	if err := os.WriteFile(availableBinary, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatalf("write executable fixture: %v", err)
	}

	for _, testCase := range []struct {
		name        string
		ffmpegPath  string
		ffprobePath string
		want        string
	}{
		{
			name:        "ffmpeg",
			ffmpegPath:  filepath.Join(tempDir, "missing-ffmpeg"),
			ffprobePath: availableBinary,
			want:        "missing-ffmpeg",
		},
		{
			name:        "ffprobe",
			ffmpegPath:  availableBinary,
			ffprobePath: filepath.Join(tempDir, "missing-ffprobe"),
			want:        "missing-ffprobe",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			_, err := NewFFmpegMediaProcessor(runtimeObjectStoreStub{}, Config{
				Bucket:      "media-bucket",
				FFmpegPath:  testCase.ffmpegPath,
				FFprobePath: testCase.ffprobePath,
			})
			if err == nil || !strings.Contains(err.Error(), testCase.want) {
				t.Fatalf("missing binary was not rejected: %v", err)
			}
		})
	}
}

func TestUploadFileStreamsArtifactFromDisk(t *testing.T) {
	payload := []byte("progressive-mp4-delivery")
	path := filepath.Join(t.TempDir(), "delivery.mp4")
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		t.Fatalf("write delivery fixture: %v", err)
	}
	store := &recordingStreamObjectStore{}
	processor := &FFmpegMediaProcessor{
		objects: store,
		config:  Config{Bucket: "media-bucket"},
	}

	digest, err := processor.uploadFile(
		context.Background(),
		path,
		"media/video/s/asset/v1/source.mp4",
		"video/mp4",
	)
	if err != nil {
		t.Fatalf("upload file: %v", err)
	}

	expectedDigest := sha256.Sum256(payload)
	if digest != "sha256:"+hex.EncodeToString(expectedDigest[:]) {
		t.Fatalf("unexpected digest %q", digest)
	}
	if !store.bodyWasFile {
		t.Fatal("delivery artifact must be streamed from an open file")
	}
	if string(store.payload) != string(payload) {
		t.Fatalf("uploaded payload mismatch: %q", store.payload)
	}
}

func TestProbeTimeoutRemainsRetryableInfrastructureFailure(t *testing.T) {
	tempDir := t.TempDir()
	slowProbe := filepath.Join(tempDir, "slow-ffprobe")
	if err := os.WriteFile(
		slowProbe,
		[]byte("#!/bin/sh\nsleep 5\n"),
		0o755,
	); err != nil {
		t.Fatalf("write slow ffprobe fixture: %v", err)
	}
	processor := &FFmpegMediaProcessor{
		objects: runtimeObjectStoreStub{},
		config:  Config{FFprobePath: slowProbe},
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := processor.probe(ctx, filepath.Join(tempDir, "source.mp4"))
	if err == nil {
		t.Fatal("cancelled probe must fail")
	}
	var rejection *mediaprocessing.RejectionError
	if errors.As(err, &rejection) {
		t.Fatalf("infrastructure timeout must not reject user content: %v", err)
	}
}

type runtimeObjectStoreStub struct{}

func (runtimeObjectStoreStub) GetObject(
	context.Context,
	string,
	string,
) (io.ReadCloser, error) {
	return io.NopCloser(strings.NewReader("")), nil
}

func (runtimeObjectStoreStub) PutObject(
	context.Context,
	string,
	string,
	string,
	io.Reader,
) error {
	return nil
}

type recordingStreamObjectStore struct {
	bodyWasFile bool
	payload     []byte
}

func (*recordingStreamObjectStore) GetObject(
	context.Context,
	string,
	string,
) (io.ReadCloser, error) {
	return io.NopCloser(strings.NewReader("")), nil
}

func (s *recordingStreamObjectStore) PutObject(
	_ context.Context,
	_ string,
	_ string,
	_ string,
	body io.Reader,
) error {
	_, s.bodyWasFile = body.(*os.File)
	payload, err := io.ReadAll(body)
	if err != nil {
		return err
	}
	s.payload = payload
	return nil
}
