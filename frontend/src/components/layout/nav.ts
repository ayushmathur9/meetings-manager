import {
  Activity,
  Building2,
  Calendar,
  LayoutDashboard,
  MapPinned,
  Settings,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

export const ADMIN_NAV: NavGroup[] = [
  {
    items: [
      { label: "Dashboard", href: "/admin", icon: LayoutDashboard },
      { label: "Prospects", href: "/admin/prospects", icon: Users },
      { label: "Companies", href: "/admin/companies", icon: Building2 },
      { label: "Meetings", href: "/admin/meetings", icon: Calendar },
      { label: "Routes", href: "/admin/routes", icon: MapPinned },
      { label: "Imports", href: "/admin/imports", icon: Upload },
    ],
  },
  {
    items: [
      { label: "Team", href: "/admin/team", icon: Users },
      { label: "Activity", href: "/admin/activity", icon: Activity },
      { label: "Settings", href: "/admin/settings", icon: Settings },
    ],
  },
];

export const SALES_NAV: NavGroup[] = [
  {
    items: [
      { label: "Dashboard", href: "/sales", icon: LayoutDashboard },
      { label: "My Prospects", href: "/sales/prospects", icon: Users },
      { label: "My Meetings", href: "/sales/meetings", icon: Calendar },
      { label: "My Route", href: "/sales/route", icon: MapPinned },
    ],
  },
];
