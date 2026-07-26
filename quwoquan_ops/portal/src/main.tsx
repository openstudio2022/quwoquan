import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './app/App.js';
import {
  PortalRuntimeLogger,
  installPortalRuntimeDiagnostics,
} from './shared/observability/runtimeLogger.js';
import './styles.css';

const portalRuntimeLogger = new PortalRuntimeLogger({
  gatewayBaseUrl: import.meta.env.VITE_PRODUCT_OPS_BASE_URL ?? '',
  resource: {
    sourceType: 'portal',
    service: 'ops-portal',
    environment: import.meta.env.VITE_APP_RUNTIME_ENV ?? 'alpha',
    'service.version': import.meta.env.VITE_BUILD_VERSION ?? '',
  },
});
installPortalRuntimeDiagnostics(portalRuntimeLogger);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
