'use strict';
// Code 128 symbol widths (ISO/IEC 15417). Internal SKU, code set B; not GS1-128.
const Code128 = (()=>{
 const patterns=('212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112').split(' ').map(x=>[...x].map(Number));
 function symbols(text){if(!text||[...text].some(c=>c.charCodeAt(0)<32||c.charCodeAt(0)>126))throw Error('El código debe contener caracteres ASCII imprimibles');const data=[...text].map(c=>c.charCodeAt(0)-32);return [104,...data,(104+data.reduce((s,v,i)=>s+v*(i+1),0))%103,106]}
 function svg(text){const ids=symbols(text);let x=12,rects='';for(const id of ids){patterns[id].forEach((w,i)=>{if(i%2===0)rects+=`<rect x="${x}" y="0" width="${w}" height="65"/>`;x+=w})}return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${x+12} 65" role="img" aria-label="Código de barras del producto" preserveAspectRatio="none"><rect width="${x+12}" height="65" fill="white"/><g fill="black">${rects}</g></svg>`}
 function decodeRuns(runs){
  function match(pos,stop=false){const n=stop?7:6;if(pos+n>runs.length)return null;const window=runs.slice(pos,pos+n),sum=window.reduce((s,v)=>s+v,0),unit=sum/(stop?13:11);if(unit<.5)return null;let best=null,error=Infinity;for(let id=stop?106:0;id<=(stop?106:105);id++){const pat=patterns[id];const e=pat.reduce((s,v,i)=>s+Math.abs(window[i]/unit-v),0)/n;if(e<error){error=e;best=id}}return error<(stop?.43:.43)?best:null}
  for(let start=0;start+18<runs.length;start+=2){const first=match(start);if(![103,104,105].includes(first))continue;let ids=[first],end=false;for(let pos=start+6;pos<runs.length-5;pos+=6){if(match(pos,true)===106 && pos+7<runs.length && runs[pos+7] >= runs.slice(pos,pos+7).reduce((sum,v)=>sum+v,0)/13*6){end=true;break}const id=match(pos);if(id==null||id>102)break;ids.push(id);if(ids.length>100)break}if(!end||ids.length<3)continue;const check=ids.pop();if((ids[0]+ids.slice(1).reduce((s,v,i)=>s+v*(i+1),0))%103!==check)continue;let mode=ids[0]===104?'B':ids[0]===105?'C':'A',out='';for(const id of ids.slice(1)){if(id===99){mode='C';continue}if(id===100){mode='B';continue}if(id===101){mode='A';continue}if(mode==='C')out+=String(id).padStart(2,'0');else out+=String.fromCharCode(mode==='B'?id+32:id<64?id+32:id-64)}if(out)return out}return null;
 }
 function decodeImage(image){
  const canvas=document.createElement('canvas'),scale=Math.min(1,1800/(image.videoWidth||image.naturalWidth||image.width));
  canvas.width=Math.round((image.videoWidth||image.naturalWidth||image.width)*scale);canvas.height=Math.round((image.videoHeight||image.naturalHeight||image.height)*scale);
  const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0,canvas.width,canvas.height);
  for(const fraction of [.5,.4,.6,.3,.7,.2,.8]){
   const row=ctx.getImageData(0,Math.floor(canvas.height*fraction),canvas.width,1).data;
   const gray=[];let lo=255,hi=0;
   for(let i=0;i<row.length;i+=4){const v=(row[i]+row[i+1]+row[i+2])/3;gray.push(v);lo=Math.min(lo,v);hi=Math.max(hi,v)}
   if(hi-lo<50)continue;
   const threshold=(lo+hi)/2;
   for(const pixels of [gray,[...gray].reverse()]){
    const start=pixels.findIndex(v=>v<threshold);if(start<0)continue;
    let dark=true,boundary=start>0?start-1+(threshold-pixels[start-1])/(pixels[start]-pixels[start-1]):0,runs=[];
    for(let i=start+1;i<pixels.length;i++){
     const next=pixels[i]<threshold;
     if(next!==dark){const edge=i-1+(threshold-pixels[i-1])/(pixels[i]-pixels[i-1]);runs.push(edge-boundary);boundary=edge;dark=next}
    }
    runs.push(pixels.length-boundary);
    const value=decodeRuns(runs);if(value)return value;
   }
  }
  return null;
 }
 return {svg,symbols,decodeImage,decodeRuns};
})();
