import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/helpers/utils";

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => (
  React.createElement(SelectPrimitive.Trigger, {
    ref,
    className: cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
      className
    ),
    ...props,
  },
    children,
    React.createElement(ChevronDown, { className: "h-4 w-4 opacity-50" })
  )
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectContent = React.forwardRef(({ className, children, position = "popper", ...props }, ref) => (
  React.createElement(SelectPrimitive.Portal, null,
    React.createElement(SelectPrimitive.Content, {
      ref,
      className: cn(
        "relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        position === "popper" && "data-[side=bottom]:translate-y-1 data-[side=top]:-translate-y-1",
        className
      ),
      position,
      ...props,
    },
      React.createElement(SelectPrimitive.ScrollUpButton, { className: "flex cursor-default items-center justify-center py-1" },
        React.createElement(ChevronUp, { className: "h-4 w-4" })
      ),
      React.createElement(SelectPrimitive.Viewport, {
        className: cn("p-1", position === "popper" && "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]")
      },
        children
      ),
      React.createElement(SelectPrimitive.ScrollDownButton, { className: "flex cursor-default items-center justify-center py-1" },
        React.createElement(ChevronDown, { className: "h-4 w-4" })
      )
    )
  )
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectItem = React.forwardRef(({ className, children, ...props }, ref) => (
  React.createElement(SelectPrimitive.Item, {
    ref,
    className: cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className
    ),
    ...props,
  },
    React.createElement("span", { className: "absolute left-2 flex h-3.5 w-3.5 items-center justify-center" },
      React.createElement(SelectPrimitive.ItemIndicator, null,
        React.createElement(Check, { className: "h-4 w-4" })
      )
    ),
    React.createElement(SelectPrimitive.ItemText, null, children)
  )
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

export {
  Select, SelectGroup, SelectValue,
  SelectTrigger, SelectContent, SelectItem,
};
