// Package processing is the production image/video pipeline behind the
// media-processing worker. Video is normalized to progressive fast-start
// H.264/AAC MP4 with cover and preview artifacts; image handling lives in
// ffmpeg_image_processor.go and produces one validated baseline for CDN
// profile derivation.
//
// 模块边界：本包只被 media processing worker 消费；对象存储经窄接口注入，
// ffmpeg/ffprobe 以外部二进制调用。今后拆分独立服务时本包随 worker 整体迁移。
package processing

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"image"
	"image/draw"
	"image/jpeg"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

// ProcessorProfile identifies this pipeline generation in descriptors and
// preview manifests.
const ProcessorProfile = "content_processing_progressive_mp4_v1"

const (
	targetKeyframeIntervalMs = 2000
	fastStartScanBytes       = 4 * 1024 * 1024
	coverJPEGQuality         = 3  // ffmpeg -q:v scale (2..31, lower is better)
	frameJPEGQuality         = 5  // preview frames tolerate stronger compression
	spriteJPEGQuality        = 80 // Go image/jpeg quality (1..100)
	defaultWorkDirFreeBytes  = 512 * 1024 * 1024
)

// ObjectStore is the narrow storage capability the pipeline needs. The
// production implementation is runtimemedia.S3PresignClient.
type ObjectStore interface {
	GetObject(ctx context.Context, bucket string, key string) (io.ReadCloser, error)
	PutObject(ctx context.Context, bucket string, key string, contentType string, body io.Reader) error
}

type Config struct {
	Bucket      string
	FFmpegPath  string
	FFprobePath string
	// WorkDir hosts per-job scratch directories; empty means os.TempDir().
	WorkDir string
	// JobTimeout bounds one asset end to end. Zero means 15 minutes.
	JobTimeout time.Duration
	// MinWorkDirFreeBytes prevents FFmpeg from beginning a job that would
	// predictably exhaust the shared scratch volume. Zero uses the commercial
	// floor; capacity failure is infrastructure-retryable, never a rejection.
	MinWorkDirFreeBytes int64
}

type FFmpegMediaProcessor struct {
	objects ObjectStore
	config  Config
}

func NewFFmpegMediaProcessor(objects ObjectStore, config Config) (*FFmpegMediaProcessor, error) {
	if objects == nil {
		return nil, fmt.Errorf("ffmpeg media processor requires an object store")
	}
	config.Bucket = strings.TrimSpace(config.Bucket)
	if config.Bucket == "" {
		return nil, fmt.Errorf("ffmpeg media processor requires a bucket")
	}
	if strings.TrimSpace(config.FFmpegPath) == "" {
		config.FFmpegPath = "ffmpeg"
	}
	if strings.TrimSpace(config.FFprobePath) == "" {
		config.FFprobePath = "ffprobe"
	}
	if config.JobTimeout <= 0 {
		config.JobTimeout = 15 * time.Minute
	}
	if config.MinWorkDirFreeBytes <= 0 {
		config.MinWorkDirFreeBytes = defaultWorkDirFreeBytes
	}
	for _, binary := range []string{config.FFmpegPath, config.FFprobePath} {
		if _, err := exec.LookPath(binary); err != nil {
			return nil, fmt.Errorf("media processing binary %q is unavailable: %w", binary, err)
		}
	}
	return &FFmpegMediaProcessor{objects: objects, config: config}, nil
}

func (p *FFmpegMediaProcessor) Process(
	ctx context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	switch strings.ToLower(strings.TrimSpace(request.MediaType)) {
	case "image":
		return p.processImage(ctx, request)
	case "video":
		// Continue through the video pipeline below.
	default:
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: fmt.Sprintf("unsupported media type %q", request.MediaType),
		}
	}
	ctx, cancel := context.WithTimeout(ctx, p.config.JobTimeout)
	defer cancel()

	workDir, err := p.createWorkDir("media-processing-")
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf("create media processing work dir: %w", err)
	}
	defer os.RemoveAll(workDir)

	sourcePath := filepath.Join(workDir, "source"+sourceExtension(request.ContentType))
	if err := p.downloadObject(ctx, request.SourceObjectKey, sourcePath); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}

	sourceProbe, err := p.probe(ctx, sourcePath)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if !sourceProbe.HasVideo || sourceProbe.VideoCodec == "" {
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: "uploaded media has no decodable video stream",
		}
	}
	if sourceProbe.DurationMs <= 0 {
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: "uploaded video duration is not readable",
		}
	}
	if sourceProbe.DurationMs > mediamodel.MaxVideoDurationMs {
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: fmt.Sprintf(
				"video duration %dms exceeds the %dms ceiling",
				sourceProbe.DurationMs,
				mediamodel.MaxVideoDurationMs,
			),
		}
	}

	// 统一转码归一：所有 UGC 视频重编码为 fast-start H.264/AAC MP4、关键帧
	// 间隔 2s。恒定归一保证 descriptor 的每个字段都来自本管线产物而不是对
	// 上传字节的猜测；已合规视频的直通复用是后续吞吐优化，不影响契约。
	deliveryPath := filepath.Join(workDir, "delivery.mp4")
	if err := p.transcode(ctx, sourcePath, deliveryPath, sourceProbe); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	deliveryProbe, err := p.probe(ctx, deliveryPath)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if !deliveryProbe.HasVideo || deliveryProbe.DurationMs <= 0 ||
		deliveryProbe.VideoCodec != "h264" || deliveryProbe.AudioCodec != "aac" {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"normalized delivery mp4 failed self-check: video=%q audio=%q duration=%dms",
			deliveryProbe.VideoCodec,
			deliveryProbe.AudioCodec,
			deliveryProbe.DurationMs,
		)
	}
	fastStart, err := hasFastStartLayout(deliveryPath)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if !fastStart {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf("normalized delivery mp4 is not fast-start")
	}

	coverPath := filepath.Join(workDir, "cover.jpg")
	if err := p.extractCover(ctx, deliveryPath, coverPath); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}

	plan, err := PlanPreviewTrack(deliveryProbe.DurationMs)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	framesDir := filepath.Join(workDir, "frames")
	if err := os.MkdirAll(framesDir, 0o755); err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf("create preview frames dir: %w", err)
	}
	if err := p.extractPreviewFrames(ctx, deliveryPath, framesDir, plan); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	spriteFiles, err := composeSprites(framesDir, workDir, plan)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}

	slices := deliverySliceKeys(request.AssetID, request.AssetVersion)
	spriteArtifacts := make([]spriteArtifact, 0, len(spriteFiles))
	for index, spritePath := range spriteFiles {
		digest, uploadErr := p.uploadFile(
			ctx,
			spritePath,
			slices.sprite(index),
			"image/jpeg",
		)
		if uploadErr != nil {
			return mediaprocessing.ProcessOutcome{}, uploadErr
		}
		spriteArtifacts = append(spriteArtifacts, spriteArtifact{
			PublicSliceKey: slices.sprite(index),
			SHA256:         digest,
			Width:          plan.Sprites[index].Width,
			Height:         plan.Sprites[index].Height,
		})
	}
	manifestJSON, err := EncodePreviewManifest(
		request.AssetID,
		request.AssetVersion,
		ProcessorProfile,
		plan,
		spriteArtifacts,
	)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if _, err := p.uploadFile(ctx, deliveryPath, slices.video, "video/mp4"); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if _, err := p.uploadFile(ctx, coverPath, slices.cover, "image/jpeg"); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if err := p.objects.PutObject(
		ctx,
		p.config.Bucket,
		slices.manifest,
		"application/json",
		bytes.NewReader(manifestJSON),
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf("upload preview manifest: %w", err)
	}

	return mediaprocessing.ProcessOutcome{
		Descriptor: mediamodel.MediaProcessingDescriptor{
			Video: mediamodel.VideoProcessingDescriptor{
				ProcessorProfile:             ProcessorProfile,
				VerifiedDurationMs:           deliveryProbe.DurationMs,
				VideoWidth:                   deliveryProbe.Width,
				VideoHeight:                  deliveryProbe.Height,
				VideoCodec:                   "h264",
				VideoContainer:               "mp4",
				VideoAudioCodec:              "aac",
				VideoKeyframeIntervalMs:      targetKeyframeIntervalMs,
				VideoFastStart:               true,
				VideoPublicSliceKey:          slices.video,
				CoverPublicSliceKey:          slices.cover,
				PreviewTrackVersion:          previewTrackVersion,
				PreviewTrackManifestSliceKey: slices.manifest,
			},
		},
	}, nil
}

func (p *FFmpegMediaProcessor) createWorkDir(prefix string) (string, error) {
	workRoot := strings.TrimSpace(p.config.WorkDir)
	if workRoot == "" {
		workRoot = os.TempDir()
	}
	var filesystem syscall.Statfs_t
	if err := syscall.Statfs(workRoot, &filesystem); err != nil {
		return "", fmt.Errorf("inspect media processing work dir %q: %w", workRoot, err)
	}
	available := int64(filesystem.Bavail) * int64(filesystem.Bsize)
	if available < p.config.MinWorkDirFreeBytes {
		return "", fmt.Errorf(
			"media processing work dir %q has %d free bytes, requires at least %d",
			workRoot,
			available,
			p.config.MinWorkDirFreeBytes,
		)
	}
	return os.MkdirTemp(workRoot, prefix)
}

type deliverySlices struct {
	prefix   string
	video    string
	cover    string
	manifest string
}

func (s deliverySlices) sprite(index int) string {
	return fmt.Sprintf("%s/preview/sprite-%03d.jpg", s.prefix, index)
}

func deliverySliceKeys(assetID string, assetVersion int64) deliverySlices {
	video := runtimemedia.BuildContentMediaPublicSliceKey(
		"video",
		assetID,
		assetVersion,
		"video/mp4",
	)
	prefix := strings.TrimSuffix(video, "/source.mp4")
	return deliverySlices{
		prefix:   prefix,
		video:    video,
		cover:    prefix + "/cover.jpg",
		manifest: prefix + "/preview/manifest.json",
	}
}

func (p *FFmpegMediaProcessor) downloadObject(
	ctx context.Context,
	objectKey string,
	targetPath string,
) error {
	body, err := p.objects.GetObject(ctx, p.config.Bucket, objectKey)
	if err != nil {
		return fmt.Errorf("download media source %q: %w", objectKey, err)
	}
	defer body.Close()
	file, err := os.Create(targetPath)
	if err != nil {
		return fmt.Errorf("create media source file: %w", err)
	}
	defer file.Close()
	if _, err := io.Copy(file, body); err != nil {
		return fmt.Errorf("write media source file: %w", err)
	}
	return nil
}

func (p *FFmpegMediaProcessor) probe(ctx context.Context, path string) (VideoProbe, error) {
	output, err := runCommand(ctx, p.config.FFprobePath,
		"-v", "error",
		"-print_format", "json",
		"-show_streams",
		"-show_format",
		path,
	)
	if err != nil {
		if ctx.Err() != nil {
			return VideoProbe{}, fmt.Errorf("media probe interrupted: %w", ctx.Err())
		}
		if isUndecodableMediaSource(err) {
			return VideoProbe{}, &mediaprocessing.RejectionError{
				Reason: "uploaded media cannot be decoded",
			}
		}
		// 外部二进制的退出、运行时库和宿主资源故障不能被固化成用户内容
		// 拒绝；只有成功 probe 后的确定性内容约束才使用 RejectionError。
		return VideoProbe{}, fmt.Errorf(
			"ffprobe execution failed: %v",
			commandFailureSummary(err),
		)
	}
	return ParseFFprobeOutput(output)
}

func (p *FFmpegMediaProcessor) transcode(
	ctx context.Context,
	sourcePath string,
	deliveryPath string,
	probe VideoProbe,
) error {
	gop := keyframeGOP(probe.FrameRate)
	args := []string{"-hide_banner", "-loglevel", "error", "-y", "-i", sourcePath}
	if !probe.HasAudio {
		// 无麦/静音录制的视频没有音轨；domain 契约要求交付 mp4 必须携带
		// AAC 音轨，这里注入等长静音而不是拒绝内容。
		args = append(args, "-f", "lavfi", "-t",
			fmt.Sprintf("%.3f", float64(probe.DurationMs)/1000.0),
			"-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
			"-map", "0:v:0", "-map", "1:a:0", "-shortest",
		)
	} else {
		args = append(args, "-map", "0:v:0", "-map", "0:a:0")
	}
	args = append(args,
		"-c:v", "libx264",
		"-preset", "veryfast",
		"-profile:v", "high",
		"-pix_fmt", "yuv420p",
		"-g", fmt.Sprintf("%d", gop),
		"-sc_threshold", "0",
		"-c:a", "aac",
		"-b:a", "128k",
		"-movflags", "+faststart",
		"-max_muxing_queue_size", "1024",
		deliveryPath,
	)
	if _, err := runCommand(ctx, p.config.FFmpegPath, args...); err != nil {
		if ctx.Err() != nil {
			return fmt.Errorf("video transcode timed out: %w", ctx.Err())
		}
		return fmt.Errorf(
			"ffmpeg transcode execution failed: %v",
			commandFailureSummary(err),
		)
	}
	return nil
}

func (p *FFmpegMediaProcessor) extractCover(
	ctx context.Context,
	deliveryPath string,
	coverPath string,
) error {
	// format=yuvj420p：JPEG 要求全范围 YUV；ffmpeg 8.x 对 studio-range 输入
	// 的 mjpeg 编码会静默失败（exit 0 且零产物）。
	if _, err := runCommand(ctx, p.config.FFmpegPath,
		"-hide_banner", "-loglevel", "error", "-y",
		"-ss", "0",
		"-i", deliveryPath,
		"-vf", "format=yuvj420p",
		"-frames:v", "1",
		"-q:v", fmt.Sprintf("%d", coverJPEGQuality),
		coverPath,
	); err != nil {
		return fmt.Errorf("extract cover frame: %w", err)
	}
	if _, err := os.Stat(coverPath); err != nil {
		return fmt.Errorf("cover frame was not produced: %w", err)
	}
	return nil
}

func (p *FFmpegMediaProcessor) extractPreviewFrames(
	ctx context.Context,
	deliveryPath string,
	framesDir string,
	plan PreviewTrackPlan,
) error {
	// round=up 保证短于一个采样周期的视频仍在 0ms 产出首帧；
	// yuvj420p 显式满足 FFmpeg 8+ 的 full-range MJPEG 编码要求。
	if _, err := runCommand(ctx, p.config.FFmpegPath,
		"-hide_banner", "-loglevel", "error", "-y",
		"-i", deliveryPath,
		"-vf", fmt.Sprintf(
			"fps=1000/%d:start_time=0:round=up,scale=%d:%d,format=yuvj420p",
			plan.FrameIntervalMs,
			plan.FrameWidth,
			plan.FrameHeight,
		),
		"-q:v", fmt.Sprintf("%d", frameJPEGQuality),
		filepath.Join(framesDir, "frame_%05d.jpg"),
	); err != nil {
		return fmt.Errorf("extract preview frames: %w", err)
	}
	return nil
}

// composeSprites tiles the extracted frames into 5-column JPEG atlases in Go,
// so any sprite count works with a single decode pass of the video.
func composeSprites(
	framesDir string,
	workDir string,
	plan PreviewTrackPlan,
) ([]string, error) {
	framePaths, err := sortedFramePaths(framesDir)
	if err != nil {
		return nil, err
	}
	if len(framePaths) == 0 {
		return nil, fmt.Errorf("preview frame extraction produced no frames")
	}
	// fps 取整可能比 plan 少一帧（时长边界）；多出的帧直接截断，缺帧时复用
	// 最后一帧填充，保证 manifest frame 数与实际 sprite 内容一致。
	spritePaths := make([]string, 0, len(plan.Sprites))
	frameCursor := 0
	for _, spritePlan := range plan.Sprites {
		canvas := image.NewRGBA(image.Rect(0, 0, spritePlan.Width, spritePlan.Height))
		for slot := 0; slot < spritePlan.FrameCount; slot++ {
			sourceIndex := frameCursor
			if sourceIndex >= len(framePaths) {
				sourceIndex = len(framePaths) - 1
			}
			frame, decodeErr := decodeJPEG(framePaths[sourceIndex])
			if decodeErr != nil {
				return nil, decodeErr
			}
			x := (slot % previewColumns) * plan.FrameWidth
			y := (slot / previewColumns) * plan.FrameHeight
			target := image.Rect(x, y, x+plan.FrameWidth, y+plan.FrameHeight)
			draw.Draw(canvas, target, frame, frame.Bounds().Min, draw.Src)
			frameCursor++
		}
		spritePath := filepath.Join(
			workDir,
			fmt.Sprintf("sprite-%03d.jpg", spritePlan.Index),
		)
		if err := encodeJPEG(spritePath, canvas); err != nil {
			return nil, err
		}
		spritePaths = append(spritePaths, spritePath)
	}
	return spritePaths, nil
}

func sortedFramePaths(framesDir string) ([]string, error) {
	entries, err := os.ReadDir(framesDir)
	if err != nil {
		return nil, fmt.Errorf("read preview frames dir: %w", err)
	}
	paths := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".jpg") {
			continue
		}
		paths = append(paths, filepath.Join(framesDir, entry.Name()))
	}
	sort.Strings(paths)
	return paths, nil
}

func decodeJPEG(path string) (image.Image, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open preview frame: %w", err)
	}
	defer file.Close()
	frame, err := jpeg.Decode(file)
	if err != nil {
		return nil, fmt.Errorf("decode preview frame %q: %w", filepath.Base(path), err)
	}
	return frame, nil
}

func encodeJPEG(path string, canvas image.Image) error {
	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create sprite file: %w", err)
	}
	defer file.Close()
	if err := jpeg.Encode(file, canvas, &jpeg.Options{Quality: spriteJPEGQuality}); err != nil {
		return fmt.Errorf("encode sprite: %w", err)
	}
	return nil
}

func (p *FFmpegMediaProcessor) uploadFile(
	ctx context.Context,
	path string,
	objectKey string,
	contentType string,
) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("open delivery artifact %q: %w", filepath.Base(path), err)
	}
	defer file.Close()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", fmt.Errorf("hash delivery artifact %q: %w", filepath.Base(path), err)
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return "", fmt.Errorf("rewind delivery artifact %q: %w", filepath.Base(path), err)
	}
	if err := p.objects.PutObject(
		ctx,
		p.config.Bucket,
		objectKey,
		contentType,
		file,
	); err != nil {
		return "", fmt.Errorf("upload delivery artifact %q: %w", objectKey, err)
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil)), nil
}

// hasFastStartLayout mirrors the media-canary check: the moov box must appear
// before mdat inside the leading bytes so playback can start while streaming.
func hasFastStartLayout(path string) (bool, error) {
	file, err := os.Open(path)
	if err != nil {
		return false, fmt.Errorf("open delivery mp4: %w", err)
	}
	defer file.Close()
	header := make([]byte, fastStartScanBytes)
	read, err := io.ReadFull(file, header)
	if err != nil && err != io.ErrUnexpectedEOF {
		return false, fmt.Errorf("read delivery mp4 header: %w", err)
	}
	header = header[:read]
	moov := bytes.Index(header, []byte("moov"))
	mdat := bytes.Index(header, []byte("mdat"))
	return moov >= 0 && (mdat < 0 || moov < mdat), nil
}

func keyframeGOP(frameRate float64) int {
	if frameRate <= 0 {
		frameRate = 30
	}
	gop := int(frameRate*float64(targetKeyframeIntervalMs)/1000.0 + 0.5)
	if gop < 1 {
		gop = 1
	}
	return gop
}

func sourceExtension(contentType string) string {
	switch strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0])) {
	case "video/mp4":
		return ".mp4"
	case "video/quicktime":
		return ".mov"
	case "video/webm":
		return ".webm"
	case "video/x-matroska":
		return ".mkv"
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/gif":
		return ".gif"
	case "image/webp":
		return ".webp"
	case "image/heic", "image/heif":
		return ".heic"
	default:
		return ".bin"
	}
}

func runCommand(ctx context.Context, binary string, args ...string) ([]byte, error) {
	command := exec.CommandContext(ctx, binary, args...)
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

type commandExecutionError struct {
	binary string
	cause  error
	stderr string
}

func (err *commandExecutionError) Error() string {
	return fmt.Sprintf("%s failed: %v: %s", err.binary, err.cause, err.stderr)
}

func (err *commandExecutionError) Unwrap() error {
	return err.cause
}

func isUndecodableMediaSource(err error) bool {
	var commandErr *commandExecutionError
	if !errors.As(err, &commandErr) {
		return false
	}
	diagnostic := strings.ToLower(commandErr.stderr)
	return strings.Contains(diagnostic, "invalid data found when processing input") ||
		strings.Contains(diagnostic, "moov atom not found")
}

func commandFailureSummary(err error) string {
	message := err.Error()
	if len(message) > 512 {
		message = message[:512]
	}
	return message
}
