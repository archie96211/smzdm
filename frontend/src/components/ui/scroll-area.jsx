import * as React from "react";
import { cn } from "@/helpers/utils";

const ScrollArea = React.forwardRef(({ className, children, ...props }, ref) => (
  React.createElement("div", {
    ref,
    className: cn("relative overflow-auto", className),
    ...props,
  }, children)
));
ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
