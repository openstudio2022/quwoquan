import { useEffect, useState } from 'react';
import { productWorkflow } from '../../generated/control-plane/productWorkflow.generated';
import { fetchExperiments, type ExperimentItem } from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function ExperimentsPage() {
  const experimentWorkflow = productWorkflow.workflows.find((item) => item.object_type === 'experiment');
  const [experiments, setExperiments] = useState<ExperimentItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    fetchExperiments()
      .then((items) => {
        setExperiments(items);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  return (
    <PageScaffold
      title="实验与灰度"
      subtitle="统一管理分桶、放量、guardrail、回滚和审计，不让实验系统与推荐策略系统各走一套发布逻辑。"
      meta={
        <>
          <span className="badge badge--neutral">5% → 25% → 50% → 100%</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实实验服务已接入' : '当前展示回退到门户样例'}
          </span>
        </>
      }
      actions={<button className="button button--primary">新建实验</button>}
      footer={
        <>
          <button className="button">查看分桶命中</button>
          <button className="button button--primary">推进到下一灰度阶段</button>
        </>
      }
    >
      <SectionCard title="实验工作流" subtitle="冻结 draft、review、running、ramping、rollback、archive 的标准生命周期">
        <div className="workflow">
          {experimentWorkflow?.states.map((state, index) => (
            <span className={`workflow-step ${index <= 2 ? 'workflow-step--active' : ''}`} key={state}>
              {state}
            </span>
          ))}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--three">
        <SectionCard title="运行中实验" subtitle="运行中实验和观测状态">
          <div className="stack-list">
            {(experiments.length > 0
              ? experiments
              : [
                  {
                    id: 'EXP-feed-layout-v3',
                    name: '发现流布局实验',
                    enabled: true,
                    policyVersion: 'mock',
                    buckets: [],
                    bucketStats: {},
                    assignedSubjects: 0,
                  },
                  {
                    id: 'EXP-rank-author-diversity',
                    name: '作者多样性实验',
                    enabled: true,
                    policyVersion: 'mock',
                    buckets: [],
                    bucketStats: {},
                    assignedSubjects: 0,
                  },
                ]
            ).map((experiment) => (
              <div className="policy-item" key={experiment.id}>
                <div>
                  <p className="item-title">{experiment.id}</p>
                  <p className="item-subtitle">
                    {experiment.name} · policy={experiment.policyVersion} · subject={experiment.assignedSubjects}
                  </p>
                </div>
                <span className={`badge ${experiment.enabled ? 'badge--success' : 'badge--warning'}`}>
                  {experiment.enabled ? 'running' : 'paused'}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Guardrail 看板" subtitle="实验放量必须绑定业务和安全 guardrail">
          <div className="insight-grid">
            <div className="insight-box">
              <p className="insight-box__title">CTR</p>
              <div className="insight-box__body">
                {remoteReady ? '按真实 bucketStats 聚合展示，当前服务已提供统计 API。' : '+3.2%，在允许波动内。'}
              </div>
            </div>
            <div className="insight-box">
              <p className="insight-box__title">投诉率</p>
              <div className="insight-box__body">0.28%，未突破 0.35% 阈值。</div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="审计与回滚" subtitle="保证放量和撤回都具备 request/trace/rollback token">
          <div className="insight-grid">
            <div className="insight-box">
              <p className="insight-box__title">rollback ready</p>
              <div className="insight-box__body">
                {remoteReady ? '控制面 rollout API 已可切换 enabled 与 bucket 权重。' : '所有运行中实验均具备可用回滚令牌。'}
              </div>
            </div>
            <div className="insight-box">
              <p className="insight-box__title">审批状态</p>
              <div className="insight-box__body">2 个实验待 review_pending 审批。</div>
            </div>
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
