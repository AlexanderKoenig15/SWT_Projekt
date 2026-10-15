import mermaid from "https://unpkg.com/mermaid@11/dist/mermaid.esm.min.mjs";

const darkText = "#1a1a1a";
const lightDiagramFills = [
  "#a3cc74",
  "#e6f4ea",
  "#e8f0fe",
  "#fce8e6",
  "#fef7e0",
  "#ffc916",
  "#ffd6d6",
  "#fff129",
];

const lightFillSelectors = lightDiagramFills
  .map(
    (fill) =>
      `.node:has(> rect[style*="fill:${fill}"]) .label,` +
      `.node:has(> rect[style*="fill:${fill}"]) .label *`,
  )
  .join(",\n");

const contrastThemeCSS = `${lightFillSelectors} {
  color: ${darkText} !important;
  fill: ${darkText} !important;
}`;

const initializeMermaid = mermaid.initialize.bind(mermaid);
mermaid.initialize = (config = {}) => {
  const themeCSS =
    typeof config.themeCSS === "string" ? config.themeCSS : "";
  return initializeMermaid({
    ...config,
    themeCSS: `${themeCSS}\n${contrastThemeCSS}`,
  });
};

mermaid.initialize({ startOnLoad: false, securityLevel: "antiscript" });

window.mermaid = mermaid;
