// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
package processing_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
	"path/filepath"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"strings"
	"sync"
	"testing"
)

type hlsCMAFRecordedObject struct {
	mimeType string
	payload  []byte
}

type hlsCMAFRecordingStore struct {
	mu      sync.Mutex
	objects map[string]hlsCMAFRecordedObject
}

func (s *hlsCMAFRecordingStore) GetObject(
	context.Context,
	string,
	string,
) (io.ReadCloser, error) {
	return nil, fmt.Errorf("not used")
}

func (s *hlsCMAFRecordingStore) PutObject(
	_ context.Context,
	_ string,
	key string,
	mimeType string,
	body io.Reader,
) error {
	payload, err := io.ReadAll(body)
	if err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.objects[key] = hlsCMAFRecordedObject{
		mimeType: mimeType,
		payload:  payload,
	}
	return nil
}

func TestPackageHLSCMAFProducesValidatedVODArtifactsAndDescriptor(t *testing.T) {
	for _, binary := range []string{"ffmpeg", "ffprobe"} {
		if _, err := exec.LookPath(binary); err != nil {
			t.Fatalf("HLS/CMAF local_contract requires %s on PATH: %v", binary, err)
		}
	}
	workDir := t.TempDir()
	sourcePath := filepath.Join(workDir, "delivery.mp4")
	command := exec.Command(
		"ffmpeg",
		"-hide_banner", "-loglevel", "error", "-y",
		"-f", "lavfi", "-i", "testsrc2=duration=2:size=540x960:rate=30",
		"-f", "lavfi", "-i", "sine=frequency=440:duration=2",
		"-map", "0:v:0", "-map", "1:a:0",
		"-c:v", "libx264", "-pix_fmt", "yuv420p",
		"-g", "60", "-sc_threshold", "0",
		"-c:a", "aac", "-shortest", sourcePath,
	)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		t.Fatalf("render HLS/CMAF source: %v: %s", err, stderr.String())
	}
	store := &hlsCMAFRecordingStore{
		objects: make(map[string]hlsCMAFRecordedObject),
	}
	processor, err := NewFFmpegMediaProcessor(store, Config{Bucket: "media"})
	if err != nil {
		t.Fatalf("build HLS/CMAF processor: %v", err)
	}
	probe, err := processor.Probe(context.Background(), sourcePath)
	if err != nil {
		t.Fatalf("probe HLS/CMAF source: %v", err)
	}
	slices := DeliverySliceKeys("asset-hls-package", 3)
	artifacts, err := processor.PackageHLSCMAF(
		context.Background(),
		sourcePath,
		workDir,
		"asset-hls-package",
		3,
		probe,
		slices,
		ProcessorProfile,
	)
	if err != nil {
		t.Fatalf("package HLS/CMAF: %v", err)
	}
	if artifacts.DescriptorVersion != 1 || artifacts.RenditionCount != 3 ||
		artifacts.DescriptorSliceKey != slices.Prefix+"/hls/descriptor.json" ||
		artifacts.MasterManifestSliceKey != slices.Prefix+"/hls/master.m3u8" {
		t.Fatalf("unexpected HLS/CMAF artifacts: %+v", artifacts)
	}

	requireObject := func(key string, mimeType string) hlsCMAFRecordedObject {
		t.Helper()
		object, found := store.objects[key]
		if !found {
			t.Fatalf("HLS/CMAF object %q is missing", key)
		}
		if object.mimeType != mimeType {
			t.Fatalf("HLS/CMAF object %q content-type=%q, want %q", key, object.mimeType, mimeType)
		}
		return object
	}
	descriptorObject := requireObject(artifacts.DescriptorSliceKey, "application/json")
	master := requireObject(
		artifacts.MasterManifestSliceKey,
		"application/vnd.apple.mpegurl",
	)
	if bytes.Count(master.payload, []byte("#EXT-X-STREAM-INF")) != artifacts.RenditionCount {
		t.Fatalf("master manifest does not expose the planned ladder: %s", master.payload)
	}
	var descriptor struct {
		Schema                 string `json:"schema"`
		AssetID                string `json:"assetId"`
		AssetVersion           int64  `json:"assetVersion"`
		DescriptorVersion      int    `json:"descriptorVersion"`
		Protocol               string `json:"protocol"`
		SegmentFormat          string `json:"segmentFormat"`
		SegmentDurationMS      int    `json:"segmentDurationMs"`
		MasterManifestSliceKey string `json:"masterManifestSliceKey"`
		FallbackVideoSliceKey  string `json:"fallbackVideoSliceKey"`
		VideoCodec             string `json:"videoCodec"`
		AudioCodec             string `json:"audioCodec"`
		Renditions             []struct {
			PlaylistSliceKey string `json:"playlistSliceKey"`
		} `json:"renditions"`
	}
	if err := json.Unmarshal(descriptorObject.payload, &descriptor); err != nil {
		t.Fatalf("decode HLS/CMAF descriptor: %v", err)
	}
	if descriptor.Schema != "quwoquan.content.hls_cmaf_descriptor" ||
		descriptor.AssetID != "asset-hls-package" || descriptor.AssetVersion != 3 ||
		descriptor.DescriptorVersion != 1 || descriptor.Protocol != "hls" ||
		descriptor.SegmentFormat != "cmaf" || descriptor.SegmentDurationMS != 2000 ||
		descriptor.MasterManifestSliceKey != artifacts.MasterManifestSliceKey ||
		descriptor.FallbackVideoSliceKey != slices.Video ||
		descriptor.VideoCodec != "h264" || descriptor.AudioCodec != "aac" ||
		len(descriptor.Renditions) != artifacts.RenditionCount {
		t.Fatalf("HLS/CMAF descriptor violates the canonical contract: %+v", descriptor)
	}
	for _, rendition := range descriptor.Renditions {
		playlist := requireObject(
			rendition.PlaylistSliceKey,
			"application/vnd.apple.mpegurl",
		)
		prefix := rendition.PlaylistSliceKey[:strings.LastIndex(rendition.PlaylistSliceKey, "/")]
		initFound := false
		segmentFound := false
		for _, line := range strings.Split(string(playlist.payload), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "#EXT-X-MAP:URI=\"") && strings.HasSuffix(line, "\"") {
				name := strings.TrimSuffix(strings.TrimPrefix(line, "#EXT-X-MAP:URI=\""), "\"")
				requireObject(prefix+"/"+name, "video/mp4")
				initFound = true
			}
			if strings.HasSuffix(line, ".m4s") {
				requireObject(prefix+"/"+line, "video/iso.segment")
				segmentFound = true
			}
		}
		if !initFound || !segmentFound ||
			!bytes.Contains(playlist.payload, []byte("#EXT-X-INDEPENDENT-SEGMENTS")) ||
			!bytes.Contains(playlist.payload, []byte("#EXT-X-ENDLIST")) {
			t.Fatalf("rendition playlist is not an independent CMAF VOD: %s", playlist.payload)
		}
	}
}
