package releaseimport

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	generated "quwoquan_service/services/content-service/generated/content/post"
)

const (
	RetiredContentTypeMigrationReceiptSchema = "quwoquan.content_retired_content_type_migration_receipt"
	RetiredContentTypeQuiescedConfirmation   = "confirmed"
)

// ErrRetiredContentTypeProjectionRecoveryRequired 阻止没有 canonical 恢复协议的原地改写。
// Data 的候选闭包、不可变事实和 fence 不能通过修改 live posts 或旧发现流恢复；
// 普通 Post 的版本、安全 revision、生命周期 outbox 也必须由既有提交事务共同推进。
// 在这两种来源的迁移协议被明确批准前，禁止先改 Post 再声称可重试修复投影。
var ErrRetiredContentTypeProjectionRecoveryRequired = errors.New("GATE_BLOCK: retired contentType migration requires an approved canonical release/lifecycle projection recovery protocol")

type RetiredContentTypeOutcome string

const (
	RetiredContentTypeMigratedVideo         RetiredContentTypeOutcome = "video"
	RetiredContentTypeMigratedImage         RetiredContentTypeOutcome = "image"
	RetiredContentTypeMigratedArticle       RetiredContentTypeOutcome = "article"
	RetiredContentTypeBlockedConflict       RetiredContentTypeOutcome = "blocked_media_conflict"
	RetiredContentTypeBlockedUnclassifiable RetiredContentTypeOutcome = "blocked_unclassifiable"
	RetiredContentTypeBlockedUnknownType    RetiredContentTypeOutcome = "blocked_unknown_content_type"
)

// RetiredContentTypePostRow 只包含显式退役输入的直接分类事实。
type RetiredContentTypePostRow struct {
	PostID           string                       `bson:"_id"`
	ContentType      string                       `bson:"contentType"`
	MediaItems       []RetiredContentTypeMediaRow `bson:"mediaItems"`
	MediaURLs        []string                     `bson:"mediaUrls"`
	VideoURL         string                       `bson:"videoUrl"`
	Body             string                       `bson:"body"`
	ArticleMarkdown  string                       `bson:"articleMarkdown"`
	SemanticDocument bson.Raw                     `bson:"semanticDocument"`
}

type RetiredContentTypeMediaRow struct {
	Kind string `bson:"kind"`
}

// ClassifyRetiredContentType 只分类 canonical 声明为退役的 exact 取值（生成投影
// generated.RetiredContentTypeValues，真相源是 _shared/types.yaml 的
// retired_enum_values）；未来未知类型绝不按媒体猜测。
// mediaItems 存在时是权威媒体序列，缺少旧 URL 不构成冲突；反向矛盾和未知
// kind 则阻断。文章载体与媒体载体并存时不猜谁是正文/嵌入素材，等待人工裁决。
// semanticDocument 的非空 BSON 字节不是正文证据（空文档也有字节）。
func ClassifyRetiredContentType(row RetiredContentTypePostRow) RetiredContentTypeOutcome {
	if !generated.IsRetiredContentType(row.ContentType) {
		return RetiredContentTypeBlockedUnknownType
	}
	media := classifyRetiredContentTypeMedia(row)
	if media != RetiredContentTypeBlockedUnclassifiable {
		if strings.TrimSpace(row.ArticleMarkdown) != "" || len(row.SemanticDocument) > 0 {
			return RetiredContentTypeBlockedConflict
		}
		return media
	}
	if strings.TrimSpace(row.Body) != "" || strings.TrimSpace(row.ArticleMarkdown) != "" {
		return RetiredContentTypeMigratedArticle
	}
	return RetiredContentTypeBlockedUnclassifiable
}

// 媒体内部先处理闭集和矛盾，再决定视频/图片；正文裁决由上层单独处理。
func classifyRetiredContentTypeMedia(row RetiredContentTypePostRow) RetiredContentTypeOutcome {
	media := RetiredContentTypeBlockedUnclassifiable
	for _, item := range row.MediaItems {
		switch item.Kind {
		case "video":
			media = RetiredContentTypeMigratedVideo
		case "image":
			if media != RetiredContentTypeMigratedVideo {
				media = RetiredContentTypeMigratedImage
			}
		default:
			return RetiredContentTypeBlockedConflict
		}
	}
	if strings.TrimSpace(row.VideoURL) != "" {
		if media == RetiredContentTypeMigratedImage {
			return RetiredContentTypeBlockedConflict
		}
		return RetiredContentTypeMigratedVideo
	}
	if len(row.MediaItems) > 0 {
		return media
	}
	for _, url := range row.MediaURLs {
		if strings.TrimSpace(url) != "" {
			return RetiredContentTypeMigratedImage
		}
	}
	return media
}

type RetiredContentTypeMigrationDecision struct {
	PostID   string                    `json:"postId"`
	Previous string                    `json:"previousContentType"`
	Outcome  RetiredContentTypeOutcome `json:"outcome"`
}

type RetiredContentTypeMigrationResult struct {
	Scanned      int                                   `json:"scanned"`
	Migrated     int                                   `json:"migrated"`
	Blocked      int                                   `json:"blocked"`
	ByOutcome    map[RetiredContentTypeOutcome]int     `json:"byOutcome"`
	BlockedPosts []RetiredContentTypeMigrationDecision `json:"blockedPosts"`
}

// MigrateRetiredContentTypes 当前只保留 fail-closed 入口，不执行任何存储操作。
// 旧版 posts -> discovery feed 两阶段写入不能恢复已提交 Post 的投影失败；
// 更不能以没有 micro 行证明旧运行没有留下部分状态。重复调用仍阻断，不虚报完成。
func MigrateRetiredContentTypes(ctx context.Context, database *mongo.Database) (RetiredContentTypeMigrationResult, error) {
	result := RetiredContentTypeMigrationResult{
		ByOutcome:    map[RetiredContentTypeOutcome]int{},
		BlockedPosts: []RetiredContentTypeMigrationDecision{},
	}
	if ctx == nil || database == nil {
		return result, fmt.Errorf("retired contentType migration context and database are required")
	}
	return result, ErrRetiredContentTypeProjectionRecoveryRequired
}

func canonicalContentTypeValues() []string {
	values := make([]string, 0, len(generated.AllowedContentTypes))
	for value := range generated.AllowedContentTypes {
		values = append(values, value)
	}
	sort.Strings(values)
	return values
}

type RetiredContentTypeMigrationReceipt struct {
	Schema            string                                `json:"schema"`
	Status            string                                `json:"status"`
	Database          string                                `json:"database"`
	MigrationMode     string                                `json:"migrationMode"`
	CanonicalSet      []string                              `json:"canonicalContentTypes"`
	Scanned           int                                   `json:"scanned"`
	Migrated          int                                   `json:"migrated"`
	Blocked           int                                   `json:"blocked"`
	ByOutcome         map[string]int                        `json:"byOutcome"`
	BlockedPosts      []RetiredContentTypeMigrationDecision `json:"blockedPosts"`
	FirstTypedBlocker string                                `json:"firstTypedBlocker"`
	GeneratedAt       time.Time                             `json:"generatedAt"`
}

type retiredContentTypeMigrationCommand struct {
	mongoURI   string
	Database   string
	ReportPath string
}

func ParseRetiredContentTypeMigrationCommand(args []string) (retiredContentTypeMigrationCommand, error) {
	flags := flag.NewFlagSet("migrate-retired-content-type", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	mongoURI := flags.String("mongo-uri", "", "Content MongoDB connection URI")
	database := flags.String("database", "", "Content MongoDB database name")
	report := flags.String("report", "", "create-once receipt destination path")
	if err := flags.Parse(args); err != nil {
		// flag 错误可能包含调用者提供的 URI，外部只返回固定的参数错误。
		return retiredContentTypeMigrationCommand{}, fmt.Errorf("invalid retired contentType migration flags")
	}
	if flags.NArg() != 0 {
		return retiredContentTypeMigrationCommand{}, fmt.Errorf("retired contentType migration does not accept positional arguments")
	}
	command := retiredContentTypeMigrationCommand{
		mongoURI: strings.TrimSpace(*mongoURI), Database: strings.TrimSpace(*database), ReportPath: strings.TrimSpace(*report),
	}
	if command.mongoURI == "" || command.Database == "" || command.ReportPath == "" {
		return retiredContentTypeMigrationCommand{}, fmt.Errorf("retired contentType migration requires --mongo-uri, --database and --report")
	}
	return command, nil
}

// RunRetiredContentTypeMigration 在连接数据库前记录恢复协议阻断证据；不把
// 零扫描/零修改误报为迁移完成。回执槽位是原子 create-once，失败也不可覆盖。
func RunRetiredContentTypeMigration(ctx context.Context, args []string) error {
	if ctx == nil {
		return fmt.Errorf("retired contentType migration context is required")
	}
	command, err := ParseRetiredContentTypeMigrationCommand(args)
	if err != nil {
		return err
	}
	if strings.TrimSpace(os.Getenv("QWQ_STORAGE_MIGRATION_MODE")) != QuiescedAtomicStorageMigrationMode {
		return fmt.Errorf("retired contentType migration requires QWQ_STORAGE_MIGRATION_MODE=%s", QuiescedAtomicStorageMigrationMode)
	}
	if strings.TrimSpace(os.Getenv("QWQ_CONTENT_POSTS_QUIESCED")) != RetiredContentTypeQuiescedConfirmation {
		return fmt.Errorf("retired contentType migration requires QWQ_CONTENT_POSTS_QUIESCED=%s", RetiredContentTypeQuiescedConfirmation)
	}
	report, err := validateRetiredContentTypeReportDestination(command.ReportPath)
	if err != nil {
		return err
	}
	receipt := RetiredContentTypeMigrationReceipt{
		Schema: RetiredContentTypeMigrationReceiptSchema, Status: "blocked", Database: command.Database,
		MigrationMode: QuiescedAtomicStorageMigrationMode, CanonicalSet: canonicalContentTypeValues(),
		ByOutcome: map[string]int{}, BlockedPosts: []RetiredContentTypeMigrationDecision{},
		FirstTypedBlocker: "canonical_projection_recovery_required",
		GeneratedAt:       time.Now().UTC().Truncate(time.Millisecond),
	}
	if err := writeRetiredContentTypeReceipt(report, receipt); err != nil {
		return errors.Join(ErrRetiredContentTypeProjectionRecoveryRequired, err)
	}
	return ErrRetiredContentTypeProjectionRecoveryRequired
}

func validateRetiredContentTypeReportDestination(path string) (string, error) {
	resolved, err := filepath.Abs(strings.TrimSpace(path))
	if err != nil || strings.TrimSpace(path) == "" || resolved == string(filepath.Separator) {
		return "", fmt.Errorf("retired contentType migration report path is invalid")
	}
	if _, err := os.Lstat(resolved); err == nil {
		return "", fmt.Errorf("retired contentType migration report already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", fmt.Errorf("inspect retired contentType migration report destination: %w", err)
	}
	// 检查全部祖先，不能只检查直接父目录而允许上层 symlink 穿透。
	for parent := filepath.Dir(resolved); ; parent = filepath.Dir(parent) {
		info, err := os.Lstat(parent)
		if err != nil {
			return "", fmt.Errorf("inspect retired contentType migration report directory: %w", err)
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("retired contentType migration report directory must be a non-symlink directory")
		}
		if parent == filepath.Dir(parent) {
			break
		}
	}
	return resolved, nil
}

func writeRetiredContentTypeReceipt(path string, receipt RetiredContentTypeMigrationReceipt) error {
	payload, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		return fmt.Errorf("encode retired contentType migration receipt: %w", err)
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create retired contentType migration receipt: %w", err)
	}
	// 保留写入失败的槽位作为失败证据；重试必须使用新的回执路径。
	defer file.Close()
	if _, err := file.Write(append(payload, '\n')); err != nil {
		return fmt.Errorf("write retired contentType migration receipt: %w", err)
	}
	if err := file.Sync(); err != nil {
		return fmt.Errorf("sync retired contentType migration receipt: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close retired contentType migration receipt: %w", err)
	}
	return nil
}
