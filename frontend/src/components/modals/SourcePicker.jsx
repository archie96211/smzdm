import React from "react";

const SOURCES = [
  { key: "smzdm", label: "什么值得买" },
  { key: "manmanbuy", label: "慢慢买" },
];

export default function SourcePicker({ value = "smzdm", onChange }) {
  function toggle(source) {
    const selected = new Set(value === "both" ? SOURCES.map((item) => item.key) : [value]);
    if (selected.has(source)) {
      if (selected.size === 1) return;
      selected.delete(source);
    } else {
      selected.add(source);
    }
    onChange(selected.size === 2 ? "both" : [...selected][0]);
  }

  return (
    <div role="group" aria-label="好价来源" className="flex flex-wrap gap-3">
      {SOURCES.map(({ key, label }) => (
        <label key={key} className="flex cursor-pointer items-center gap-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-sm">
          <input type="checkbox" checked={value === "both" || value === key}
            onChange={() => toggle(key)} className="h-4 w-4 accent-primary" />
          <span>{label}</span>
        </label>
      ))}
    </div>
  );
}
