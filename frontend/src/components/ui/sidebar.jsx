import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { PanelLeft } from "lucide-react";
import { cn } from "@/helpers/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";

const SIDEBAR_WIDTH = "16rem";
const SIDEBAR_WIDTH_ICON = "3rem";
const SIDEBAR_KEYBOARD_SHORTCUT = "b";

const SidebarContext = React.createContext(null);

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider.");
  }
  return context;
}

function SidebarProvider({
  defaultOpen = true,
  open: openProp,
  onOpenChange: setOpenProp,
  className,
  style,
  children,
  ...props
}) {
  const [isMobile, setIsMobile] = React.useState(false);
  const [openMobile, setOpenMobile] = React.useState(false);
  const [_open, _setOpen] = React.useState(defaultOpen);
  const open = openProp ?? _open;

  React.useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  const setOpen = React.useCallback((value) => {
    const openState = typeof value === "function" ? value(open) : value;
    if (setOpenProp) {
      setOpenProp(openState);
    } else {
      _setOpen(openState);
    }
    try {
      document.cookie = `sidebar_state=${openState}; path=/; max-age=${60 * 60 * 24 * 7}`;
    } catch {}
  }, [setOpenProp, open]);

  const toggleSidebar = React.useCallback(() => {
    return isMobile ? setOpenMobile((o) => !o) : setOpen((o) => !o);
  }, [isMobile, setOpen, setOpenMobile]);

  React.useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  const state = open ? "expanded" : "collapsed";

  const contextValue = React.useMemo(() => ({
    state, open, setOpen, isMobile, openMobile, setOpenMobile, toggleSidebar,
  }), [state, open, setOpen, isMobile, openMobile, setOpenMobile, toggleSidebar]);

  return React.createElement(SidebarContext.Provider, { value: contextValue },
    React.createElement(TooltipProvider, { delayDuration: 0 },
      React.createElement("div", {
        "data-slot": "sidebar-wrapper",
        style: {
          "--sidebar-width": SIDEBAR_WIDTH,
          "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
          ...style,
        },
        className: cn("group/sidebar-wrapper flex min-h-svh w-full has-data-[variant=inset]:bg-sidebar", className),
        ...props,
      }, children)
    )
  );
}

function Sidebar({
  side = "left",
  variant = "sidebar",
  collapsible = "offcanvas",
  className,
  children,
  ...props
}) {
  const { isMobile, state, openMobile, setOpenMobile } = useSidebar();

  if (collapsible === "none") {
    return React.createElement("div", {
      "data-slot": "sidebar",
      className: cn("flex h-full w-(--sidebar-width) flex-col bg-sidebar text-sidebar-foreground", className),
      ...props,
    }, children);
  }

  if (isMobile) {
    return React.createElement("div", {
      "data-slot": "sidebar",
      "data-mobile": "true",
      className: cn(
        "fixed inset-y-0 z-50 w-[18rem] bg-sidebar transition-transform duration-200",
        side === "left" ? "left-0 border-r" : "right-0 border-l",
        openMobile ? "translate-x-0" : side === "left" ? "-translate-x-full" : "translate-x-full",
        className
      ),
      ...props,
    }, children);
  }

  return React.createElement("div", {
    className: "group peer hidden text-sidebar-foreground md:block",
    "data-state": state,
    "data-collapsible": state === "collapsed" ? collapsible : "",
    "data-variant": variant,
    "data-side": side,
    "data-slot": "sidebar",
  },
    React.createElement("div", {
      "data-slot": "sidebar-gap",
      className: cn(
        "relative w-(--sidebar-width) bg-transparent transition-[width] duration-200 ease-linear",
        "group-data-[collapsible=offcanvas]:w-0",
        "group-data-[side=right]:rotate-180",
        variant === "floating" || variant === "inset"
          ? "group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+1rem)]"
          : "group-data-[collapsible=icon]:w-(--sidebar-width-icon)"
      ),
    }),
    React.createElement("div", {
      "data-slot": "sidebar-container",
      className: cn(
        "fixed inset-y-0 z-10 hidden h-svh w-(--sidebar-width) transition-[left,right,width] duration-200 ease-linear md:flex",
        side === "left"
          ? "left-0 group-data-[collapsible=offcanvas]:left-[calc(var(--sidebar-width)*-1)]"
          : "right-0 group-data-[collapsible=offcanvas]:right-[calc(var(--sidebar-width)*-1)]",
        variant === "floating" || variant === "inset"
          ? "p-2 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+1rem+2px)]"
          : "group-data-[collapsible=icon]:w-(--sidebar-width-icon) group-data-[side=left]:border-r group-data-[side=right]:border-l",
        className
      ),
      ...props,
    },
      React.createElement("div", {
        "data-sidebar": "sidebar",
        "data-slot": "sidebar-inner",
        className: "flex h-full w-full flex-col bg-sidebar group-data-[variant=floating]:rounded-lg group-data-[variant=floating]:border group-data-[variant=floating]:border-sidebar-border group-data-[variant=floating]:shadow-sm",
      }, children)
    )
  );
}

function SidebarTrigger({ className, onClick, ...props }) {
  const { toggleSidebar } = useSidebar();
  return React.createElement(Button, {
    "data-sidebar": "trigger",
    "data-slot": "sidebar-trigger",
    variant: "ghost",
    size: "icon",
    className: cn("size-7", className),
    onClick: (event) => { onClick?.(event); toggleSidebar(); },
    ...props,
  },
    React.createElement(PanelLeft, null),
    React.createElement("span", { className: "sr-only" }, "Toggle Sidebar")
  );
}

function SidebarRail({ className, ...props }) {
  const { toggleSidebar } = useSidebar();
  return React.createElement("button", {
    "data-sidebar": "rail",
    "data-slot": "sidebar-rail",
    "aria-label": "Toggle Sidebar",
    tabIndex: -1,
    onClick: toggleSidebar,
    title: "Toggle Sidebar",
    className: cn(
      "absolute inset-y-0 z-20 hidden w-4 -translate-x-1/2 transition-all ease-linear right-0 after:absolute after:inset-y-0 after:left-1/2 after:w-[2px] hover:after:bg-sidebar-border sm:flex",
      "group-data-[collapsible=offcanvas]:translate-x-0 group-data-[collapsible=offcanvas]:after:left-full hover:group-data-[collapsible=offcanvas]:bg-sidebar",
      className
    ),
    ...props,
  });
}

function SidebarInset({ className, ...props }) {
  return React.createElement("main", {
    "data-slot": "sidebar-inset",
    className: cn(
      "relative flex w-full flex-1 flex-col bg-background",
      "md:peer-data-[variant=inset]:m-2 md:peer-data-[variant=inset]:ml-0 md:peer-data-[variant=inset]:rounded-xl md:peer-data-[variant=inset]:shadow-sm md:peer-data-[variant=inset]:peer-data-[state=collapsed]:ml-2",
      className
    ),
    ...props,
  });
}

function SidebarInput({ className, ...props }) {
  return React.createElement(Input, {
    "data-slot": "sidebar-input",
    "data-sidebar": "input",
    className: cn("h-8 w-full bg-background shadow-none", className),
    ...props,
  });
}

function SidebarHeader({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-header",
    "data-sidebar": "header",
    className: cn("flex flex-col gap-2 p-2", className),
    ...props,
  });
}

function SidebarFooter({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-footer",
    "data-sidebar": "footer",
    className: cn("flex flex-col gap-2 p-2", className),
    ...props,
  });
}

function SidebarSeparator({ className, ...props }) {
  return React.createElement(Separator, {
    "data-slot": "sidebar-separator",
    "data-sidebar": "separator",
    className: cn("mx-2 w-auto bg-sidebar-border", className),
    ...props,
  });
}

function SidebarContent({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-content",
    "data-sidebar": "content",
    className: cn("flex min-h-0 flex-1 flex-col gap-2 overflow-auto group-data-[collapsible=icon]:overflow-hidden", className),
    ...props,
  });
}

function SidebarGroup({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-group",
    "data-sidebar": "group",
    className: cn("relative flex w-full min-w-0 flex-col p-2", className),
    ...props,
  });
}

function SidebarGroupLabel({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-group-label",
    "data-sidebar": "group-label",
    className: cn(
      "flex h-8 shrink-0 items-center rounded-md px-2 text-xs font-medium text-sidebar-foreground/70 transition-[margin,opacity] duration-200 ease-linear",
      "group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0",
      className
    ),
    ...props,
  });
}

function SidebarGroupAction({ className, asChild = false, ...props }) {
  const Comp = asChild ? Slot : "button";
  return React.createElement(Comp, {
    "data-slot": "sidebar-group-action",
    "data-sidebar": "group-action",
    className: cn(
      "absolute top-3.5 right-3 flex aspect-square w-5 items-center justify-center rounded-md p-0 text-sidebar-foreground transition-transform hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      "group-data-[collapsible=icon]:hidden",
      className
    ),
    ...props,
  });
}

function SidebarGroupContent({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-group-content",
    "data-sidebar": "group-content",
    className: cn("w-full text-sm", className),
    ...props,
  });
}

function SidebarMenu({ className, ...props }) {
  return React.createElement("ul", {
    "data-slot": "sidebar-menu",
    "data-sidebar": "menu",
    className: cn("flex w-full min-w-0 flex-col gap-1", className),
    ...props,
  });
}

function SidebarMenuItem({ className, ...props }) {
  return React.createElement("li", {
    "data-slot": "sidebar-menu-item",
    "data-sidebar": "menu-item",
    className: cn("group/menu-item relative", className),
    ...props,
  });
}

const sidebarMenuButtonVariants = cva(
  "peer/menu-button flex w-full items-center gap-2 overflow-hidden rounded-md p-2 text-left text-sm transition-[width,height,padding] group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:p-2! hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        outline: "bg-background hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      },
      size: {
        default: "h-8 text-sm",
        sm: "h-7 text-xs",
        lg: "h-12 text-sm group-data-[collapsible=icon]:p-0!",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

function SidebarMenuButton({
  asChild = false,
  isActive = false,
  variant = "default",
  size = "default",
  tooltip,
  className,
  ...props
}) {
  const Comp = asChild ? Slot : "button";
  const { isMobile, state } = useSidebar();

  const button = React.createElement(Comp, {
    "data-slot": "sidebar-menu-button",
    "data-sidebar": "menu-button",
    "data-size": size,
    "data-active": isActive,
    className: cn(sidebarMenuButtonVariants({ variant, size }), className),
    ...props,
  });

  if (!tooltip) return button;

  const tooltipProps = typeof tooltip === "string" ? { children: tooltip } : tooltip;

  return React.createElement(Tooltip, null,
    React.createElement(TooltipTrigger, { asChild: true }, button),
    React.createElement(TooltipContent, {
      side: "right",
      align: "center",
      hidden: state !== "collapsed" || isMobile,
      ...tooltipProps,
    })
  );
}

function SidebarMenuAction({ className, asChild = false, showOnHover = false, ...props }) {
  const Comp = asChild ? Slot : "button";
  return React.createElement(Comp, {
    "data-slot": "sidebar-menu-action",
    "data-sidebar": "menu-action",
    className: cn(
      "absolute top-1.5 right-1 flex aspect-square w-5 items-center justify-center rounded-md p-0 text-sidebar-foreground transition-transform peer-hover/menu-button:text-sidebar-accent-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      "group-data-[collapsible=icon]:hidden",
      showOnHover && "group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 md:opacity-0",
      className
    ),
    ...props,
  });
}

function SidebarMenuBadge({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-menu-badge",
    "data-sidebar": "menu-badge",
    className: cn(
      "pointer-events-none absolute right-1 flex h-5 min-w-5 select-none items-center justify-center rounded-md text-xs font-medium tabular-nums text-sidebar-foreground/70",
      "group-data-[collapsible=icon]:hidden",
      className
    ),
    ...props,
  });
}

function SidebarMenuSkeleton({ className, ...props }) {
  return React.createElement("div", {
    "data-slot": "sidebar-menu-skeleton",
    className: cn("flex h-8 items-center gap-2 rounded-md px-2", className),
    ...props,
  },
    React.createElement(Skeleton, { className: "size-4 rounded-md" }),
    React.createElement(Skeleton, { className: "h-4 flex-1 max-w-[--skeleton-width]" })
  );
}

export {
  SidebarProvider, Sidebar, SidebarTrigger, SidebarRail, SidebarInset,
  SidebarInput, SidebarHeader, SidebarFooter, SidebarSeparator,
  SidebarContent, SidebarGroup, SidebarGroupLabel, SidebarGroupAction,
  SidebarGroupContent, SidebarMenu, SidebarMenuItem, SidebarMenuButton,
  SidebarMenuAction, SidebarMenuBadge, SidebarMenuSkeleton,
  useSidebar,
};
