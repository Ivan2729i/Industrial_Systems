/** Relative count concentration on a geographic grid; not temperature or burned area. */
export function densityImage(rows: {latitude:number;longitude:number;count?:number}[], cellDegrees=1) {
  const width=1440, height=720, radius=Math.min(5,Math.max(2,Math.round(cellDegrees*2))), grid=new Float32Array(width*height)
  for (const row of rows) {
    const x=Math.floor((row.longitude+180)/360*width), y=Math.floor((90-row.latitude)/180*height)
    for(let dy=-radius;dy<=radius;dy++) for(let dx=-radius;dx<=radius;dx++) {
      const yy=y+dy
      if(yy<0 || yy>=height) continue
      const xx=((x+dx)%width+width)%width
      grid[yy*width+xx]+=(row.count??1)*Math.exp(-(dx*dx+dy*dy)/Math.max(1,radius*radius/3))
    }
  }
  let max=0
  for(const v of grid) max=Math.max(max,v)
  const canvas=document.createElement('canvas'); canvas.width=width;canvas.height=height
  const context=canvas.getContext('2d')!, pixels=context.createImageData(width,height)
  for(let i=0;i<grid.length;i++) {
    const t=Math.log1p(grid[i])/Math.log1p(max||1), j=i*4
    pixels.data[j]=210+Math.round(30*t);pixels.data[j+1]=Math.round(150-105*t);pixels.data[j+2]=40
    pixels.data[j+3]=Math.round(Math.min(.5,t*t*.5)*255)
  }
  context.putImageData(pixels,0,0)
  return canvas.toDataURL()
}
