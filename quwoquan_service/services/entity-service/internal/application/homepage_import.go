package application

import (
	"context"
	"strings"
	"time"
)

// ImportedHomepageInput 是数据工程 publish 实体（page.md 三件套）→ 主页读模型的
// 导入投影输入。字段语义与 contracts/metadata/entity/homepage/projections/
// homepage_introduction*.yaml 同源；由 cmd/homepage-import 从 publish 树构建。
type ImportedHomepageInput struct {
	// EntityRef 是数据工程实体相对引用（如 地点/景区/九寨沟），用于幂等查找。
	EntityRef            string
	Title                string
	HomepageType         string
	City                 string
	IntroductionMarkdown string
	IntroductionAssets   []HomepageIntroductionAsset
	// CategoryTags 承载 _entity.json.tagRefs（Entity 类型 + Topic 地理/主题标签），
	// 与 content-service import 导 entities.tagRefs 同源（WP3 统一打标）。
	CategoryTags []string
	SourceTaskID string
}

// HomepageImportReport 汇总一次导入的幂等结果（审计证据随 import report 落盘）。
// EntityRefToHomepageID 是数据工程 entityRef → 运行库 homepageId 的映射产物
// （WP4 覆盖账本核对面消费：coverage 索引/运营核对用它换算 introduction URL）。
type HomepageImportReport struct {
	Created               []string          `json:"created"`
	Updated               []string          `json:"updated"`
	Skipped               []string          `json:"skipped"`
	EntityRefToHomepageID map[string]string `json:"entityRefToHomepageId"`
}

// UpsertImportedHomepages 幂等灌入数据工程主页投影：
//   - 已存在（按 entityRef/title 经 resolveHomepageLocked 命中）→ 只更新
//     introduction 投影字段与空缺的基础字段（不覆盖运营/认领侧已有编辑）；
//   - 不存在 → 创建并直接发布（sourceType=official_seed，与 publish 语义一致）。
//
// 全部变更共享一次快照持久化；search projector 事件在锁外逐个补发。
func (s *HomepageService) UpsertImportedHomepages(
	ctx context.Context,
	inputs []ImportedHomepageInput,
) (HomepageImportReport, error) {
	report := HomepageImportReport{
		Created:               []string{},
		Updated:               []string{},
		Skipped:               []string{},
		EntityRefToHomepageID: map[string]string{},
	}
	var emits []ProjectorEvent

	s.mu.Lock()
	now := time.Now().UTC()
	for _, input := range inputs {
		title := strings.TrimSpace(input.Title)
		if title == "" || validateHomepageInput(HomepageInput{Title: title, HomepageType: input.HomepageType}) != nil {
			report.Skipped = append(report.Skipped, input.EntityRef)
			continue
		}
		homepage, found := s.resolveHomepageLocked(input.EntityRef)
		if !found {
			homepage, found = s.resolveHomepageLocked(title)
		}
		if found {
			applyImportedProjection(homepage, input, now)
			report.Updated = append(report.Updated, homepage.ID)
			report.EntityRefToHomepageID[input.EntityRef] = homepage.ID
		} else {
			id := s.nextID("homepage")
			homepage = &Homepage{
				ID:                 id,
				Title:              title,
				HomepageType:       strings.TrimSpace(input.HomepageType),
				CanonicalEntityID:  canonicalEntityIDFromTypeAndTitle(input.HomepageType, title),
				ObjectPageTemplate: objectPageTemplate(input.HomepageType, ""),
				Status:             "published",
				SourceType:         "official_seed",
				ClaimStatus:        "unclaimed",
				City:               strings.TrimSpace(input.City),
				CreatedAt:          now,
				PublishedAt:        &now,
			}
			applyImportedProjection(homepage, input, now)
			applyDefaultShellData(homepage)
			s.homepages[id] = homepage
			report.Created = append(report.Created, id)
			report.EntityRefToHomepageID[input.EntityRef] = id
		}
		out := cloneHomepage(homepage)
		emits = append(emits, ProjectorEvent{
			Type:       ProjectorEventHomepageUpserted,
			HomepageID: out.ID,
			Homepage:   &out,
		})
	}
	err := s.persistLocked(ctx)
	s.mu.Unlock()
	if err != nil {
		return report, err
	}
	for _, event := range emits {
		s.emitSearchIndex(ctx, event)
	}
	return report, nil
}

// applyImportedProjection 把投影字段写入主页：introduction 永远以数据工程最新
// 发布为准；categoryTags 在数据工程有打标时以最新为准（标签唯一真相源是
// publish/tags 契约树，无打标不清空既有值）；封面/城市只在原值为空时补齐
// （保护认领方/运营侧的既有编辑）。
func applyImportedProjection(homepage *Homepage, input ImportedHomepageInput, now time.Time) {
	homepage.IntroductionMarkdown = strings.TrimSpace(input.IntroductionMarkdown)
	homepage.IntroductionAssets = cloneIntroductionAssets(input.IntroductionAssets)
	if len(input.CategoryTags) > 0 {
		homepage.CategoryTags = cloneStrings(input.CategoryTags)
	}
	if strings.TrimSpace(homepage.CoverURL) == "" {
		homepage.CoverURL = coverURLFromIntroductionAssets(homepage.IntroductionAssets)
	}
	if strings.TrimSpace(homepage.City) == "" {
		homepage.City = strings.TrimSpace(input.City)
	}
	homepage.UpdatedAt = now
}
