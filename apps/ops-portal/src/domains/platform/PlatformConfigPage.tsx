import { platformConfigSchema } from '../../generated/control-plane/platformConfig.generated.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';

export function PlatformConfigPage() {
  return (
    <PageScaffold
      title="Platform Ops / 配置与可靠性"
      subtitle="统一管理 `sys.*` 运行时参数、发布阶段、回滚准备度和健康基线，严格区别于 `ops.*` 业务配置。"
      meta={
        <>
          <span className="badge badge--neutral">sys.* only</span>
          <span className="badge badge--warning">高风险项必须灰度</span>
        </>
      }
      actions={<button className="button button--primary">创建配置发布单</button>}
      footer={
        <>
          <button className="button">查看变更 diff</button>
          <button className="button button--primary">提交灰度申请</button>
        </>
      }
    >
      <SectionCard title="运行时参数清单" subtitle="当前视图使用 config_schema.yaml 驱动，禁止前端手写第二套配置表">
        <table className="table">
          <thead>
            <tr>
              <th>配置项</th>
              <th>默认值</th>
              <th>scope</th>
              <th>reload</th>
              <th>risk</th>
            </tr>
          </thead>
          <tbody>
            {platformConfigSchema.configs.map((config) => (
              <tr key={config.key}>
                <td>{config.key}</td>
                <td>{String(config.default)}</td>
                <td>{config.scope}</td>
                <td>{config.reload}</td>
                <td>{config.risk_level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
