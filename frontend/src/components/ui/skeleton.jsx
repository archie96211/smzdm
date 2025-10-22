import * as React from "react";
import { cn } from "@/helpers/utils";

function Skeleton({ className, ...props }) {
  return React.createElement("div", {
    className: cn("animate-pulse rounded-md bg-muted", className),
    ...props,
  });
}

export { Skeleton };
