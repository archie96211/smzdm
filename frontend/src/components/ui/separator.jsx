import * as React from "react";
import { cn } from "@/helpers/utils";

const Separator = React.forwardRef(({ className, orientation = "horizontal", ...props }, ref) => (
  React.createElement("div", {
    ref,
    role: "separator",
    className: cn(
      "shrink-0 bg-border",
      orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
      className
    ),
    ...props,
  })
));
Separator.displayName = "Separator";

export { Separator };
