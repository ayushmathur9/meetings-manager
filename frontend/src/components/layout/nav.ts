import {
  Activity,
  BookOpen,
  Building2,
  Calendar,
  FileText,
  LayoutDashboard,
  MapPinned,
  RefreshCw,
  Settings,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** External tool whose URL comes from runtime config (/app-config); opens in a new tab. */
  external?: "quote_builder";
}

const QUOTE_BUILDER: NavItem = { label: "Quote Builder", href: "#quote-builder", icon: FileText, external: "quote_builder" };

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
      { label: "Route Planner", href: "/admin/routes", icon: MapPinned },
      { label: "Imports", href: "/admin/imports", icon: Upload },
    ],
  },
  {
    label: "Tools",
    items: [QUOTE_BUILDER, { label: "SOP", href: "/admin/sop", icon: BookOpen }],
  },
  {
    label: "Admin",
    items: [
      { label: "CRM Sync", href: "/admin/crm-sync", icon: RefreshCw },
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
  {
    label: "Tools",
    items: [QUOTE_BUILDER, { label: "SOP", href: "/sales/sop", icon: BookOpen }],
  },
];
