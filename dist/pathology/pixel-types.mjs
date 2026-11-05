// See LICENSE and THIRD_PARTY_NOTICES.md.
var PATHOLOGY_PIXEL_FEATURE_UNITS = {
  red: "RGB8-code-value",
  green: "RGB8-code-value",
  blue: "RGB8-code-value",
  optical_density_red: "negative-ln((RGB8+1)/256)-proxy",
  optical_density_green: "negative-ln((RGB8+1)/256)-proxy",
  optical_density_blue: "negative-ln((RGB8+1)/256)-proxy",
  local_mean_luma: "RGB8-luma-code-value",
  local_std_luma: "RGB8-luma-code-value"
};
export { PATHOLOGY_PIXEL_FEATURE_UNITS };
