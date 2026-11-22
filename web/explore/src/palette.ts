import source from "../../../art/palette.json?raw";
import { Color } from "three/webgpu";

const palette = JSON.parse(source) as { colors: Record<string, { srgb_hex: string }> };
export const swatch = (name: string) => new Color(palette.colors[name].srgb_hex);
