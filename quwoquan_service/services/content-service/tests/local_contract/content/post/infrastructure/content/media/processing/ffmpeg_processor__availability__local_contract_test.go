package processing_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"strings"
	"testing"
	"time"

	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
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
		Objects: store,
		Config:  Config{Bucket: "media-bucket"},
	}

	digest, err := processor.UploadFile(
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
		Objects: runtimeObjectStoreStub{},
		Config:  Config{FFprobePath: slowProbe},
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := processor.Probe(ctx, filepath.Join(tempDir, "source.mp4"))
	if err == nil {
		t.Fatal("cancelled probe must fail")
	}
	var rejection *mediaprocessing.RejectionError
	if errors.As(err, &rejection) {
		t.Fatalf("infrastructure timeout must not reject user content: %v", err)
	}
}

func TestFFmpegCommandExitRemainsRetryableInfrastructureFailure(t *testing.T) {
	tempDir := t.TempDir()
	failingProbe := filepath.Join(tempDir, "failing-ffprobe")
	if err := os.WriteFile(
		failingProbe,
		[]byte("#!/bin/sh\nexit 1\n"),
		0o755,
	); err != nil {
		t.Fatalf("write failing ffprobe fixture: %v", err)
	}
	processor := &FFmpegMediaProcessor{
		Objects: runtimeObjectStoreStub{},
		Config:  Config{FFprobePath: failingProbe},
	}

	_, err := processor.Probe(context.Background(), filepath.Join(tempDir, "source.mp4"))
	if err == nil {
		t.Fatal("failed ffprobe command must fail")
	}
	var rejection *mediaprocessing.RejectionError
	if errors.As(err, &rejection) {
		t.Fatalf("ffprobe runtime failure must remain retryable: %v", err)
	}
	if !strings.Contains(err.Error(), "ffprobe execution failed") {
		t.Fatalf("ffprobe failure classification drift: %v", err)
	}
}

func TestFFprobeUndecodableSourceDiagnosticIsRejected(t *testing.T) {
	tempDir := t.TempDir()
	failingProbe := filepath.Join(tempDir, "invalid-source-ffprobe")
	if err := os.WriteFile(
		failingProbe,
		[]byte(
			"#!/bin/sh\n"+
				"echo 'moov atom not found' >&2\n"+
				"echo 'Invalid data found when processing input' >&2\n"+
				"exit 1\n",
		),
		0o755,
	); err != nil {
		t.Fatalf("write invalid source ffprobe fixture: %v", err)
	}
	processor := &FFmpegMediaProcessor{
		Objects: runtimeObjectStoreStub{},
		Config:  Config{FFprobePath: failingProbe},
	}

	_, err := processor.Probe(context.Background(), filepath.Join(tempDir, "source.mp4"))
	var rejection *mediaprocessing.RejectionError
	if !errors.As(err, &rejection) {
		t.Fatalf("undecodable source must reject, got %v", err)
	}
	if rejection.Reason != "uploaded media cannot be decoded" {
		t.Fatalf("rejection reason=%q", rejection.Reason)
	}
}

func TestFFmpegInvalidNALDiagnosticIsRejectedAfterSuccessfulProbe(t *testing.T) {
	tempDir := t.TempDir()
	probe := filepath.Join(tempDir, "valid-source-ffprobe")
	if err := os.WriteFile(
		probe,
		[]byte(
			"#!/bin/sh\n"+
				"echo '{\"streams\":[{\"codec_type\":\"video\",\"codec_name\":\"h264\",\"width\":16,\"height\":16,\"avg_frame_rate\":\"5/1\",\"duration\":\"0.4\"},{\"codec_type\":\"audio\",\"codec_name\":\"aac\"}],\"format\":{\"duration\":\"0.4\"}}'\n",
		),
		0o755,
	); err != nil {
		t.Fatalf("write ffprobe fixture: %v", err)
	}
	transcoder := filepath.Join(tempDir, "invalid-nal-ffmpeg")
	if err := os.WriteFile(
		transcoder,
		[]byte(
			"#!/bin/sh\n"+
				"echo 'Invalid NAL unit size (342198404 > 20).' >&2\n"+
				"echo 'Error splitting the input into NAL units.' >&2\n"+
				"exit 69\n",
		),
		0o755,
	); err != nil {
		t.Fatalf("write ffmpeg fixture: %v", err)
	}
	processor := &FFmpegMediaProcessor{
		Objects: runtimeObjectStoreStub{},
		Config: Config{
			Bucket:              "media-bucket",
			FFmpegPath:          transcoder,
			FFprobePath:         probe,
			WorkDir:             tempDir,
			JobTimeout:          time.Second,
			MinWorkDirFreeBytes: 1,
		},
	}

	_, err := processor.Process(context.Background(), mediaprocessing.ProcessRequest{
		AssetID:         "asset-invalid-nal",
		AssetVersion:    2,
		SourceObjectKey: "media/source/invalid.mp4",
		MediaType:       "video",
		ContentType:     "video/mp4",
		FileSize:        128,
	})
	var rejection *mediaprocessing.RejectionError
	if !errors.As(err, &rejection) {
		t.Fatalf("invalid NAL source must reject without poisoning readiness, got %v", err)
	}
	if rejection.Reason != "uploaded media cannot be decoded" {
		t.Fatalf("rejection reason=%q", rejection.Reason)
	}
}

func TestWorkDirCapacityGuardFailsBeforeStartingMediaJob(t *testing.T) {
	processor := &FFmpegMediaProcessor{
		Objects: runtimeObjectStoreStub{},
		Config: Config{
			WorkDir:             t.TempDir(),
			MinWorkDirFreeBytes: int64(^uint64(0) >> 1),
		},
	}

	if _, err := processor.CreateWorkDir("capacity-guard-"); err == nil {
		t.Fatal("insufficient workdir capacity must block a new media job")
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
