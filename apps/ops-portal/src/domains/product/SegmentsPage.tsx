import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function SegmentsPage() {
  return (
    <PageScaffold
      title="标签与分群"
      subtitle="统一承接事件、标签、分群和实验目标人群，供 IA 配置、实验灰度和推荐策略共用。"
      meta={
        <>
          <span className="badge badge--neutral">Segment / TagRule</span>
          <span className="badge badge--success">支持 IA 与实验复用</span>
        </>
      }
      actions={<button className="button button--primary">创建分群</button>}
    >
      <SectionCard title="分群概览" subtitle="当前交付为门户承接骨架，后续将接入事件与指标真相源">
        <div className="insight-grid">
          <div className="insight-box">
            <p className="insight-box__title">高活跃创作者</p>
            <div className="insight-box__body">14.2 万用户，用于新内容扶持与创作任务触达。</div>
          </div>
          <div className="insight-box">
            <p className="insight-box__title">高投诉风险用户</p>
            <div className="insight-box__body">2,840 用户，用于治理优先级与客服提醒。</div>
          </div>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
