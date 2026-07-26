import { useEffect, useMemo, useState } from 'react';

import { productAuditSchema } from '../../generated/control-plane/productAudit.generated.js';
import {
  fetchPlatformAudits,
  fetchProductAudits,
  type PlatformAuditItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

interface AuditRow extends PlatformAuditItem {
  plane: 'platform' | 'product';
}

export function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [keyword, setKeyword] = useState('');
  const [planeFilter, setPlaneFilter] = useState<'all' | 'platform' | 'product'>('all');

  useEffect(() => {
    Promise.all([fetchPlatformAudits(), fetchProductAudits()])
      .then(([platformItems, productItems]) => {
        const merged: AuditRow[] = [
          ...platformItems.map((item) => ({ ...item, plane: 'platform' as const })),
          ...productItems.map((item) => ({ ...item, plane: 'product' as const })),
        ].sort((left, right) => (right.at || '').localeCompare(left.at || ''));
        setRows(merged);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  const filtered = useMemo(() => {
    const trimmed = keyword.trim().toLowerCase();
    return rows.filter((row) => {
      if (planeFilter !== 'all' && row.plane !== planeFilter) {
        return false;
      }
      if (!trimmed) {
        return true;
      }
      return [row.objectType, row.objectId, row.action, row.actor, row.workflowRef, row.requestId, row.traceId]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(trimmed));
    });
  }, [keyword, planeFilter, rows]);

  return (
    <PageScaffold
      title="审计与变更"
      subtitle="统一检索平台与产品控制面的真实审计事实：actor、workflow、request/trace、回滚令牌全链路可回溯。"
      meta={
        <>
          <span className="badge badge--neutral">Audit</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? `已加载 ${rows.length} 条审计事实` : '等待控制面连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
    >
      <SectionCard title="检索" subtitle="按对象、动作、actor、workflowRef、requestId、traceId 过滤">
        <div className="toolbar-row">
          <label className="toolbar-field">
            <span>关键字</span>
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="objectId / action / actor / traceId..."
            />
          </label>
          <label className="toolbar-field">
            <span>控制面</span>
            <select value={planeFilter} onChange={(event) => setPlaneFilter(event.target.value as typeof planeFilter)}>
              <option value="all">全部</option>
              <option value="platform">platform</option>
              <option value="product">product</option>
            </select>
          </label>
          <span className="badge badge--neutral">{filtered.length} / {rows.length}</span>
        </div>
      </SectionCard>

      <SectionCard title="审计事实" subtitle="按时间倒序；每条事实由后端在危险动作执行时同步落库">
        <table className="table">
          <thead>
            <tr>
              <th>时间</th>
              <th>面</th>
              <th>对象</th>
              <th>动作</th>
              <th>actor</th>
              <th>危险级别</th>
              <th>workflow / rollback</th>
              <th>trace</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 100).map((row) => (
              <tr key={`${row.plane}:${row.objectType}:${row.objectId}:${row.at}:${row.action}`}>
                <td>{row.at}</td>
                <td>{row.plane}</td>
                <td>
                  {row.objectType} / {row.objectId}
                </td>
                <td>{row.action}</td>
                <td>{row.actor}</td>
                <td>{row.dangerLevel}</td>
                <td>
                  {row.workflowRef ?? '-'}
                  {row.rollbackToken ? ` · ${row.rollbackToken}` : ''}
                </td>
                <td>{row.traceId}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <div className="inline-note">
            {remoteReady ? '没有匹配的审计事实。' : '控制面可达后将展示真实审计时间线。'}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="审计事件 schema" subtitle="由 audit_schema.yaml 生成，不允许在 UI 再手写第二套危险动作字段">
        <table className="table">
          <thead>
            <tr>
              <th>事件</th>
              <th>对象</th>
              <th>危险级别</th>
              <th>必填字段</th>
            </tr>
          </thead>
          <tbody>
            {productAuditSchema.events.map((event) => (
              <tr key={event.audit_id}>
                <td>{event.label}</td>
                <td>{event.object_type}</td>
                <td>{event.danger_level}</td>
                <td>{event.required_fields.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
