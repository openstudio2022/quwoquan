import { useEffect, useState } from 'react';

import {
  fetchExperiments,
  updateExperimentRollout,
  type ExperimentCatalogItem,
  type ExperimentVariant,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

const EXPERIMENT_STATUSES = ['draft', 'scheduled', 'running', 'paused', 'ended'] as const;
const TOTAL_BASIS_POINTS = 10000;

function statusTone(status: string): string {
  if (status === 'running') {
    return 'success';
  }
  if (status === 'paused' || status === 'scheduled') {
    return 'warning';
  }
  return 'neutral';
}

interface RolloutDraft {
  status: string;
  variants: ExperimentVariant[];
}

export function ExperimentOperationsPage() {
  const [experiments, setExperiments] = useState<ExperimentCatalogItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, RolloutDraft>>({});

  const loadExperiments = () =>
    fetchExperiments()
      .then((items) => {
        setExperiments(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });

  useEffect(() => {
    void loadExperiments();
  }, []);

  const draftFor = (experiment: ExperimentCatalogItem): RolloutDraft =>
    drafts[experiment.id] ?? {
      status: experiment.status,
      variants: experiment.variants.map((variant) => ({ ...variant })),
    };

  const updateDraft = (experiment: ExperimentCatalogItem, next: RolloutDraft) => {
    setDrafts((current) => ({ ...current, [experiment.id]: next }));
  };

  const draftTotal = (draft: RolloutDraft): number =>
    draft.variants.reduce((sum, variant) => sum + (variant.allocationBasisPoints || 0), 0);

  const submitRollout = (experiment: ExperimentCatalogItem) => {
    const draft = draftFor(experiment);
    updateExperimentRollout({
      experimentId: experiment.id,
      expectedVersion: experiment.experimentRevision,
      status: draft.status,
      variants: draft.variants,
    })
      .then(() => {
        setActionMessage(`实验 ${experiment.key} rollout 已提交`);
        setRuntimeError(null);
        return loadExperiments();
      })
      .catch((error) => setRuntimeError(coerceRuntimeError(error)));
  };

  return (
    <PageScaffold
      title="实验运营"
      subtitle="ExperimentPolicyActivated 单轨：状态与变体权重原子重分配（If-Match 版本前置，权重总和必须精确 10000）。"
      meta={
        <>
          <span className="badge badge--neutral">Product Ops</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '实验目录已接入' : '等待实验目录连接'}
          </span>
          <span className="badge badge--neutral">experiments={remoteReady ? experiments.length : '—'}</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
    >
      {actionMessage ? (
        <div className="inline-note">{actionMessage}</div>
      ) : null}
      <SectionCard
        title="实验目录"
        subtitle="全部数据来自 /control-plane/product/experiments 真实目录；分桶统计由 ExperimentAssignmentFact 投影。"
      >
        <div className="stack-list">
          {experiments.map((experiment) => {
            const draft = draftFor(experiment);
            const total = draftTotal(draft);
            const totalValid = total === TOTAL_BASIS_POINTS;
            return (
              <div className="policy-item" key={experiment.id}>
                <div style={{ width: '100%' }}>
                  <p className="item-title">
                    {experiment.key}
                    <span className={`badge badge--${statusTone(experiment.status)}`} style={{ marginLeft: 8 }}>
                      {experiment.status}
                    </span>
                  </p>
                  <p className="item-subtitle">
                    revision={experiment.experimentRevision} · assignedSubjects={experiment.assignedSubjects}
                  </p>
                  <div className="badge-row">
                    {experiment.variants.map((variant) => (
                      <span className="badge badge--neutral" key={variant.key}>
                        {variant.key}: {(variant.allocationBasisPoints / 100).toFixed(1)}% · assigned=
                        {experiment.variantStats[variant.key] ?? 0}
                      </span>
                    ))}
                  </div>
                  <div className="form-row" style={{ marginTop: 8 }}>
                    <label>
                      状态
                      <select
                        value={draft.status}
                        onChange={(event) =>
                          updateDraft(experiment, { ...draft, status: event.target.value })
                        }
                      >
                        {EXPERIMENT_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </label>
                    {draft.variants.map((variant, index) => (
                      <label key={variant.key}>
                        {variant.key} 权重（bp）
                        <input
                          type="number"
                          min={0}
                          max={TOTAL_BASIS_POINTS}
                          value={variant.allocationBasisPoints}
                          onChange={(event) => {
                            const nextVariants = draft.variants.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, allocationBasisPoints: Number(event.target.value) }
                                : item,
                            );
                            updateDraft(experiment, { ...draft, variants: nextVariants });
                          }}
                        />
                      </label>
                    ))}
                    <span className={`badge ${totalValid ? 'badge--success' : 'badge--danger'}`}>
                      总和 {total} / {TOTAL_BASIS_POINTS}
                    </span>
                    <button
                      className="button button--primary"
                      disabled={!totalValid}
                      onClick={() => submitRollout(experiment)}
                    >
                      提交 rollout（If-Match v{experiment.experimentRevision}）
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
          {remoteReady && experiments.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">暂无实验</p>
                <p className="item-subtitle">经 CreateExperiment 发布首个 revision 后会在此展示。</p>
              </div>
              <span className="badge badge--neutral">0</span>
            </div>
          ) : null}
          {!remoteReady && !runtimeError ? (
            <div className="policy-item">
              <div>
                <p className="item-title">正在读取实验目录</p>
                <p className="item-subtitle">未取得真实目录时不显示合成状态。</p>
              </div>
              <span className="badge badge--neutral">loading</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
