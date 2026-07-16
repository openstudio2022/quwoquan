import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';

type ScenarioKind = 'entityHomepages' | 'circlesOps' | 'xiaoquComments';

const scenarioConfig = {
  entityHomepages: {
    title: '实体主页运营',
    subtitle: '跟踪大学与旅行摄影主页的资料完整度、关联内容、关联圈子与问小趣入口。',
    badge: 'entity_homepage',
    rows: [
      ['北京大学', 'university', '资料/内容/圈子已接入', 'published'],
      ['西湖旅行摄影机位', 'travel_photo', '机位/作品/圈子已接入', 'published'],
      ['大理洱海旅行摄影', 'travel_photo', '等待更多作品回填', 'watching'],
    ],
  },
  circlesOps: {
    title: '圈子运营',
    subtitle: '按推荐、我的、校园、旅行摄影四场景观察曝光、点击、加入与内容发布闭环。',
    badge: 'circle_scenario',
    rows: [
      ['推荐', 'featured', 'CTR / join rate / publish attach', 'live'],
      ['校园', 'campus', '大学主页导流与校友圈加入', 'live'],
      ['旅行摄影', 'travel', '机位主页与作品沉淀', 'live'],
    ],
  },
  xiaoquComments: {
    title: '小趣评论审核',
    subtitle: '集中查看用户 @小趣、主动点评、纠错和继续追问的审核队列。',
    badge: 'assistant_comment',
    rows: [
      ['用户主动 @小趣', 'user_mention', '待抽检回复质量与引用来源', 'review'],
      ['高质量作品主动点评', 'quality_boost', '需要审核推广边界', 'review'],
      ['用户纠错', 'correction', '等待运营确认是否修正', 'pending'],
    ],
  },
} as const;

export function ProductScenarioOpsPage({ kind }: { kind: ScenarioKind }) {
  const config = scenarioConfig[kind];
  return (
    <PageScaffold
      title={config.title}
      subtitle={config.subtitle}
      meta={
        <>
          <span className="badge badge--neutral">{config.badge}</span>
          <span className="badge badge--success">beta 可观测</span>
        </>
      }
      actions={<button className="button button--primary">导出运营日报</button>}
    >
      <div className="section-grid section-grid--cards">
        <div className="kpi-card">
          <span className="kpi-card__label">L1 产品旅程</span>
          <strong>90%+</strong>
          <span>五栏主旅程 beta 验证目标</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-card__label">L2 业务质量</span>
          <strong>CTR / Join / Reply</strong>
          <span>统一从 product-ops event summary 聚合</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-card__label">L3/L4 健康</span>
          <strong>RED + Health</strong>
          <span>gateway、product-ops、ops-portal 同栈检查</span>
        </div>
      </div>

      <SectionCard title="运营对象队列" subtitle="所有对象均带 surface / feedRequestId / homepageId 或 circleId 维度">
        <table className="table">
          <thead>
            <tr>
              <th>对象</th>
              <th>类型</th>
              <th>当前状态</th>
              <th>队列</th>
            </tr>
          </thead>
          <tbody>
            {config.rows.map(([name, type, summary, status]) => (
              <tr key={`${kind}-${name}`}>
                <td>{name}</td>
                <td>{type}</td>
                <td>{summary}</td>
                <td>
                  <span className={`badge badge--${status === 'live' || status === 'published' ? 'success' : 'warning'}`}>
                    {status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
