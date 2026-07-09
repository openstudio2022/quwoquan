import type { LucideIcon } from 'lucide-react';
import {
  BadgeCheck,
  BookOpenText,
  Boxes,
  ChartArea,
  ChartColumn,
  ChartSpline,
  FlaskConical,
  History,
  LayoutDashboard,
  Network,
  PanelLeftClose,
  Rocket,
  ServerCog,
  Settings2,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  UsersRound,
} from 'lucide-react';

const iconMap: Record<string, LucideIcon> = {
  'badge-check': BadgeCheck,
  'book-open-text': BookOpenText,
  boxes: Boxes,
  'chart-area': ChartArea,
  'chart-column': ChartColumn,
  'chart-spline': ChartSpline,
  'flask-conical': FlaskConical,
  history: History,
  'layout-dashboard': LayoutDashboard,
  network: Network,
  'panel-left-close': PanelLeftClose,
  rocket: Rocket,
  'server-cog': ServerCog,
  'settings-2': Settings2,
  'shield-check': ShieldCheck,
  'shield-alert': ShieldAlert,
  sparkles: Sparkles,
  'users-round': UsersRound,
};

export function getPortalIcon(name: string): LucideIcon {
  return iconMap[name] ?? LayoutDashboard;
}
