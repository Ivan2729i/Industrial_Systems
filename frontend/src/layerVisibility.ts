export type LayerView = 'modis' | 'viirs' | 'h3' | 'harmonized'
/** Visibility never removes entities or destroys data sources. */
export function setLayerVisibility(layers: Partial<Record<LayerView, {show:boolean}>>, active:LayerView) {
  for (const [name, layer] of Object.entries(layers)) if (layer) layer.show=name===active
}
