import React from "react";

// Outline adaptation of the Bark mark; see assets/Bark-LICENSE.txt.
export default function BarkIcon({ size = 18, ...props }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...props}>
      <path d="M8 9h8v6H8zM8 8 3 6v12l5-2V8ZM16 8l5-2v12l-5-2V8ZM3 8 1 9l2 6M21 8l2 7-2 1" />
    </svg>
  );
}
