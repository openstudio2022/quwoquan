import { productAuditSchema } from '../../generated/control-plane/productAudit.generated.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';

export function AuditPage() {
  return (
    <PageScaffold
      title="审计与变更"
      subtitle="统一检索治理动作、推荐策略变更、实验放量和配置发布，确保 trace、request、workflow、evidence 全链路可回溯。"
      meta={
        <>
          <span className="badge badge--neutral">Audit</span>
          <span className="badge badge--success">高风险动作审计完整</span>
        </>
      }
    >
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
