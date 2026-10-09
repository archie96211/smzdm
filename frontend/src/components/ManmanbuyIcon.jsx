import React from "react";
import mark from "@/assets/manmanbuy-mark.png";

// Monochrome mask derived from the official 慢 mark: https://static.manmanbuy.com/res/logo1011.png
export default function ManmanbuyIcon({ size = 18, ...props }) {
  const mask = `url(${mark}) center / 140% 140% no-repeat`;
  return <span aria-hidden="true" {...props} style={{ display: "inline-block", width: size,
    height: size, flexShrink: 0, backgroundColor: "currentColor", mask, WebkitMask: mask }} />;
}
