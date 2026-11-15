/** Relative count concentration on a geographic grid; not temperature or burned area. */
export function densityImage(rows: {latitude:number;longitude:number;count?:number}[], cellDegrees=1,bbox='world') {
  const rectangle=(bbox==='world'?[-180,-90,180,90]:bbox.split(',').map(Number)) as [number,number,number,number]
  const [west,south,east,north]=rectangle,span=east>west?east-west:east+360-west
  const width=1536, height=Math.max(256,Math.min(1024,Math.round(1536*(north-south)/span))), radius=Math.min(14,Math.max(6,Math.round(cellDegrees/span*1536))), grid=new Float32Array(width*height)
  for (const row of rows) {
    const x=Math.floor((((row.longitude-west)%360+360)%360)/span*width), y=Math.floor((north-row.latitude)/(north-south)*height)
    for(let dy=-radius;dy<=radius;dy++) for(let dx=-radius;dx<=radius;dx++) {
      const yy=y+dy
      if(yy<0 || yy>=height) continue
      const xx=((x+dx)%width+width)%width
      grid[yy*width+xx]+=(row.count??1)*Math.exp(-(dx*dx+dy*dy)/Math.max(1,radius*radius/3))
    }
  }
  const values=Array.from(grid).filter(v=>v>0).sort((a,b)=>a-b)
  const max=values[Math.floor(values.length*.98)]||1
  const canvas=document.createElement('canvas'); canvas.width=width;canvas.height=height
  const context=canvas.getContext('2d')!, pixels=context.createImageData(width,height)
  for(let i=0;i<grid.length;i++) {
    const t=Math.log1p(grid[i])/Math.log1p(max||1), j=i*4
    pixels.data[j]=210+Math.round(30*t);pixels.data[j+1]=Math.round(35+175*t);pixels.data[j+2]=40
    pixels.data[j+3]=Math.round(Math.min(.9,Math.pow(t,.6)*.9)*255)
  }
  context.putImageData(pixels,0,0)
  return {image:canvas.toDataURL(),rectangle}
}
