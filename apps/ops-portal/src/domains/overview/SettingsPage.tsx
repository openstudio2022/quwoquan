import { portalShell } from '../../generated/control-plane/portalShell.generated';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function SettingsPage() {
  return (
    <PageScaffold
      title="系统设置"
      subtitle="门户级环境切换、通知、工作台视图和全局搜索能力在这里统一观察。"
      meta={
        <>
          <span className="badge badge--neutral">Portal Settings</span>
          <span className="badge badge--success">继承统一壳层元数据</span>
        </>
      }
    >
      <div className="section-grid section-grid--two">
        <SectionCard title="环境与上下文" subtitle="来自 portal_shell.yaml 的环境和 context switchers">
          <div className="badge-row">
            {portalShell.supported_environments.map((environment) => (
              <span className="badge badge--neutral" key={environment}>
                {environment}
              </span>
            ))}
          </div>
          <div className="badge-row" style={{ marginTop: 12 }}>
            {portalShell.context_switchers.map((item) => (
              <span className="badge badge--warning" key={item}>
                {item}
              </span>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="通知与工作台" subtitle="统一收敛审批、SLA、灰度与 guardrail 提醒">
          <div className="badge-row">
            {portalShell.notification_channels.map((channel) => (
              <span className="badge badge--success" key={channel}>
                {channel}
              </span>
            ))}
          </div>
          <div className="stack-list" style={{ marginTop: 12 }}>
            {portalShell.workbench_views.map((view) => (
              <div className="timeline-item" key={view.id}>
                <div>
                  <p className="item-title">{view.label}</p>
                  <p className="item-subtitle">工作台视图 ID：{view.id}</p>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
