package processing

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

const (
	hlsCMAFDescriptorSchema  = "quwoquan.content.hls_cmaf_descriptor"
	hlsCMAFDescriptorVersion = 1
	hlsCMAFSegmentDurationMS = 2000
)

type HLSCMAFRendition struct {
	ID               string `json:"id"`
	Width            int    `json:"width"`
	Height           int    `json:"height"`
	VideoBitrateBPS  int    `json:"videoBitrateBps"`
	AudioBitrateBPS  int    `json:"audioBitrateBps"`
	PlaylistSliceKey string `json:"playlistSliceKey"`
}

type hlsCMAFDescriptor struct {
	Schema                 string             `json:"schema"`
	AssetID                string             `json:"assetId"`
	AssetVersion           int64              `json:"assetVersion"`
	DescriptorVersion      int                `json:"descriptorVersion"`
	ProcessorProfile       string             `json:"processorProfile"`
	Protocol               string             `json:"protocol"`
	SegmentFormat          string             `json:"segmentFormat"`
	SegmentDurationMS      int                `json:"segmentDurationMs"`
	MasterManifestSliceKey string             `json:"masterManifestSliceKey"`
	FallbackVideoSliceKey  string             `json:"fallbackVideoSliceKey"`
	VideoCodec             string             `json:"videoCodec"`
	AudioCodec             string             `json:"audioCodec"`
	Renditions             []HLSCMAFRendition `json:"renditions"`
}

type HLSCMAFArtifacts struct {
	DescriptorVersion      int
	DescriptorSliceKey     string
	MasterManifestSliceKey string
	RenditionCount         int
}

type hlsCMAFLadderEntry struct {
	ID              string
	TargetHeight    int
	VideoBitrateBPS int
	AudioBitrateBPS int
}

var hlsCMAFLadder = []hlsCMAFLadderEntry{
	{ID: "360p", TargetHeight: 360, VideoBitrateBPS: 700_000, AudioBitrateBPS: 96_000},
	{ID: "540p", TargetHeight: 540, VideoBitrateBPS: 1_400_000, AudioBitrateBPS: 128_000},
	{ID: "720p", TargetHeight: 720, VideoBitrateBPS: 2_800_000, AudioBitrateBPS: 128_000},
}

func PlanHLSCMAFRenditions(width int, height int) ([]HLSCMAFRendition, error) {
	if width <= 0 || height <= 0 {
		return nil, fmt.Errorf("HLS/CMAF ladder requires positive source dimensions")
	}
	result := make([]HLSCMAFRendition, 0, len(hlsCMAFLadder))
	seenDimensions := make(map[string]struct{}, len(hlsCMAFLadder))
	for _, entry := range hlsCMAFLadder {
		targetHeight := entry.TargetHeight
		if targetHeight > height {
			targetHeight = height
		}
		if targetHeight%2 != 0 {
			targetHeight--
		}
		if targetHeight < 2 {
			continue
		}
		targetWidth := nearestEven(float64(width) * float64(targetHeight) / float64(height))
		if targetWidth < 2 {
			continue
		}
		dimensionKey := fmt.Sprintf("%dx%d", targetWidth, targetHeight)
		if _, duplicate := seenDimensions[dimensionKey]; duplicate {
			continue
		}
		seenDimensions[dimensionKey] = struct{}{}
		result = append(result, HLSCMAFRendition{
			ID:              entry.ID,
			Width:           targetWidth,
			Height:          targetHeight,
			VideoBitrateBPS: entry.VideoBitrateBPS,
			AudioBitrateBPS: entry.AudioBitrateBPS,
		})
		if targetHeight == height {
			break
		}
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("HLS/CMAF ladder produced no rendition")
	}
	return result, nil
}

func nearestEven(value float64) int {
	return int(math.Floor(value/2.0+0.5)) * 2
}

func (p *FFmpegMediaProcessor) PackageHLSCMAF(
	ctx context.Context,
	deliveryPath string,
	workDir string,
	requestAssetID string,
	requestAssetVersion int64,
	probe VideoProbe,
	slices DeliverySlices,
	processorProfile string,
) (HLSCMAFArtifacts, error) {
	renditions, err := PlanHLSCMAFRenditions(probe.Width, probe.Height)
	if err != nil {
		return HLSCMAFArtifacts{}, err
	}
	hlsDir := filepath.Join(workDir, "hls")
	for index := range renditions {
		if err := os.MkdirAll(filepath.Join(hlsDir, fmt.Sprintf("v%d", index)), 0o755); err != nil {
			return HLSCMAFArtifacts{}, fmt.Errorf("create HLS/CMAF rendition directory: %w", err)
		}
	}
	if err := p.packageHLSCMAFLocally(ctx, deliveryPath, hlsDir, probe, renditions); err != nil {
		return HLSCMAFArtifacts{}, err
	}

	for index := range renditions {
		renditions[index].PlaylistSliceKey = fmt.Sprintf("%s/hls/v%d/index.m3u8", slices.Prefix, index)
	}
	masterSliceKey := slices.Prefix + "/hls/master.m3u8"
	descriptorSliceKey := slices.Prefix + "/hls/descriptor.json"
	descriptorBytes, err := json.Marshal(hlsCMAFDescriptor{
		Schema:                 hlsCMAFDescriptorSchema,
		AssetID:                requestAssetID,
		AssetVersion:           requestAssetVersion,
		DescriptorVersion:      hlsCMAFDescriptorVersion,
		ProcessorProfile:       processorProfile,
		Protocol:               "hls",
		SegmentFormat:          "cmaf",
		SegmentDurationMS:      hlsCMAFSegmentDurationMS,
		MasterManifestSliceKey: masterSliceKey,
		FallbackVideoSliceKey:  slices.Video,
		VideoCodec:             "h264",
		AudioCodec:             "aac",
		Renditions:             renditions,
	})
	if err != nil {
		return HLSCMAFArtifacts{}, fmt.Errorf("encode HLS/CMAF descriptor: %w", err)
	}
	if err := p.uploadHLSCMAFDirectory(ctx, hlsDir, slices.Prefix+"/hls"); err != nil {
		return HLSCMAFArtifacts{}, err
	}
	if err := p.Objects.PutObject(
		ctx,
		p.Config.Bucket,
		descriptorSliceKey,
		"application/json",
		bytes.NewReader(descriptorBytes),
	); err != nil {
		return HLSCMAFArtifacts{}, fmt.Errorf("upload HLS/CMAF descriptor: %w", err)
	}
	return HLSCMAFArtifacts{
		DescriptorVersion:      hlsCMAFDescriptorVersion,
		DescriptorSliceKey:     descriptorSliceKey,
		MasterManifestSliceKey: masterSliceKey,
		RenditionCount:         len(renditions),
	}, nil
}

func (p *FFmpegMediaProcessor) packageHLSCMAFLocally(
	ctx context.Context,
	deliveryPath string,
	hlsDir string,
	probe VideoProbe,
	renditions []HLSCMAFRendition,
) error {
	filterParts := make([]string, 0, len(renditions)+1)
	if len(renditions) == 1 {
		filterParts = append(filterParts, fmt.Sprintf(
			"[0:v]scale=-2:'trunc(min(%d,ih)/2)*2'[v0out]",
			renditions[0].Height,
		))
	} else {
		inputs := make([]string, len(renditions))
		for index := range renditions {
			inputs[index] = fmt.Sprintf("[v%d]", index)
		}
		filterParts = append(filterParts, fmt.Sprintf(
			"[0:v]split=%d%s",
			len(renditions),
			strings.Join(inputs, ""),
		))
		for index, rendition := range renditions {
			filterParts = append(filterParts, fmt.Sprintf(
				"[v%d]scale=-2:'trunc(min(%d,ih)/2)*2'[v%dout]",
				index,
				rendition.Height,
				index,
			))
		}
	}
	args := []string{
		"-hide_banner", "-loglevel", "error", "-y",
		"-i", deliveryPath,
		"-filter_complex", strings.Join(filterParts, ";"),
	}
	gop := strconv.Itoa(keyframeGOP(probe.FrameRate))
	streamMap := make([]string, 0, len(renditions))
	for index, rendition := range renditions {
		streamIndex := strconv.Itoa(index)
		args = append(args,
			"-map", fmt.Sprintf("[v%dout]", index),
			"-map", "0:a:0",
			"-c:v:"+streamIndex, "libx264",
			"-profile:v:"+streamIndex, "high",
			"-pix_fmt:v:"+streamIndex, "yuv420p",
			"-b:v:"+streamIndex, strconv.Itoa(rendition.VideoBitrateBPS),
			"-maxrate:v:"+streamIndex, strconv.Itoa(rendition.VideoBitrateBPS*11/10),
			"-bufsize:v:"+streamIndex, strconv.Itoa(rendition.VideoBitrateBPS*2),
			"-g:v:"+streamIndex, gop,
			"-keyint_min:v:"+streamIndex, gop,
			"-sc_threshold:v:"+streamIndex, "0",
			"-c:a:"+streamIndex, "aac",
			"-b:a:"+streamIndex, strconv.Itoa(rendition.AudioBitrateBPS),
		)
		streamMap = append(streamMap, fmt.Sprintf("v:%d,a:%d", index, index))
	}
	args = append(args,
		"-f", "hls",
		"-hls_time", "2",
		"-hls_playlist_type", "vod",
		"-hls_segment_type", "fmp4",
		"-hls_flags", "independent_segments",
		"-hls_fmp4_init_filename", "init.mp4",
		"-hls_segment_filename", "v%v/segment_%05d.m4s",
		"-master_pl_name", "master.m3u8",
		"-var_stream_map", strings.Join(streamMap, " "),
		"v%v/index.m3u8",
	)
	if _, err := runCommandInDir(ctx, hlsDir, p.Config.FFmpegPath, args...); err != nil {
		if ctx.Err() != nil {
			return fmt.Errorf("HLS/CMAF packaging timed out: %w", ctx.Err())
		}
		return fmt.Errorf("HLS/CMAF packaging failed: %v", commandFailureSummary(err))
	}
	return validateHLSCMAFPackage(hlsDir, len(renditions))
}

func validateHLSCMAFPackage(hlsDir string, renditionCount int) error {
	master, err := os.ReadFile(filepath.Join(hlsDir, "master.m3u8"))
	if err != nil {
		return fmt.Errorf("read HLS master manifest: %w", err)
	}
	if !bytes.HasPrefix(master, []byte("#EXTM3U")) ||
		bytes.Count(master, []byte("#EXT-X-STREAM-INF")) != renditionCount {
		return fmt.Errorf("HLS master manifest does not declare the planned rendition set")
	}
	for index := 0; index < renditionCount; index++ {
		playlist, readErr := os.ReadFile(filepath.Join(hlsDir, fmt.Sprintf("v%d/index.m3u8", index)))
		if readErr != nil {
			return fmt.Errorf("read HLS rendition %d playlist: %w", index, readErr)
		}
		for _, marker := range [][]byte{
			[]byte("#EXT-X-INDEPENDENT-SEGMENTS"),
			[]byte("#EXT-X-MAP"),
			[]byte("#EXT-X-ENDLIST"),
			[]byte(".m4s"),
		} {
			if !bytes.Contains(playlist, marker) {
				return fmt.Errorf("HLS rendition %d playlist is missing %s", index, marker)
			}
		}
	}
	return nil
}

func (p *FFmpegMediaProcessor) uploadHLSCMAFDirectory(
	ctx context.Context,
	hlsDir string,
	publicPrefix string,
) error {
	return filepath.WalkDir(hlsDir, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(hlsDir, path)
		if err != nil {
			return err
		}
		mimeType, err := hlsCMAFMimeType(relative)
		if err != nil {
			return err
		}
		_, err = p.UploadFile(
			ctx,
			path,
			strings.TrimSuffix(publicPrefix, "/")+"/"+filepath.ToSlash(relative),
			mimeType,
		)
		return err
	})
}

func hlsCMAFMimeType(path string) (string, error) {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".m3u8":
		return "application/vnd.apple.mpegurl", nil
	case ".m4s":
		return "video/iso.segment", nil
	case ".mp4":
		return "video/mp4", nil
	default:
		return "", fmt.Errorf("unsupported HLS/CMAF artifact %q", path)
	}
}

func runCommandInDir(
	ctx context.Context,
	dir string,
	binary string,
	args ...string,
) ([]byte, error) {
	command := exec.CommandContext(ctx, binary, args...)
	command.Dir = dir
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		return nil, &commandExecutionError{
			binary: binary,
			cause:  err,
			stderr: strings.TrimSpace(stderr.String()),
		}
	}
	return stdout.Bytes(), nil
}
