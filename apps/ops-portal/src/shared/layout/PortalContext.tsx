import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

import { portalShell } from '../../generated/control-plane/portalShell.generated.js';

type SupportedEnvironment = (typeof portalShell.supported_environments)[number];

type PortalScope = {
  environment: string;
  setEnvironment: (environment: string) => void;
};

const PortalScopeContext = createContext<PortalScope | null>(null);

export function PortalScopeProvider({ children }: { children: ReactNode }) {
  const [environment, setEnvironmentState] = useState<SupportedEnvironment>(portalShell.default_environment);
  const value = useMemo(
    () => ({
      environment,
      setEnvironment: (nextEnvironment: string) => {
        setEnvironmentState(nextEnvironment as SupportedEnvironment);
      },
    }),
    [environment],
  );
  return <PortalScopeContext.Provider value={value}>{children}</PortalScopeContext.Provider>;
}

export function usePortalScope() {
  const value = useContext(PortalScopeContext);
  if (!value) {
    throw new Error('usePortalScope must be used within PortalScopeProvider');
  }
  return value;
}
