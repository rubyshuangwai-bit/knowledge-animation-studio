// Generic topic-independent diagrams. New mechanisms belong in project/custom.js.
const SECS=TL.shots.map((s,i)=>({s,i,y0:i*1000,st:fxStart(i),v:TL.assets.visuals[i]}));
CAM0={x:960,y:430,z:.95};CAM=[];
for(const sc of SECS)if(sc.i){const cu=FX_CUTS[sc.i-1];CAM.push(cu&&(cu.kind==='curl'||cu.kind==='erase')?[cu.t0,cu.tj,960,sc.y0+430,.95,'cut']:[sc.s.start,sc.s.start+.6,960,sc.y0+430,.95]);}
function stLabel(text,x,y,w,h,size=60,color=C.ink){
 size=Math.min(size,Math.max(48,Math.floor(h/1.16)));text=String(text);g.textAlign='left';g.textBaseline='middle';g.fillStyle=color;
 while(size>48){g.font=hand(size,700);if(g.measureText(text).width<=w)break;size-=2;}
 g.font=hand(size,700);const lines=[];let line='';
 for(const ch of text){if(g.measureText(line+ch).width>w&&line){lines.push(line);line='';}line+=ch;}if(line)lines.push(line);
 if(lines.length*size*1.16>h+8)throw new Error('Label does not fit at readable size: '+text+'; shorten label or use a custom scene');
 lines.forEach((s,i)=>g.fillText(s,x,y+h/2+(i-(lines.length-1)/2)*size*1.16));
}
function stBox(s,x,y,w,h=145,color=C.ink,fill=C.white){g.fillStyle=fill;g.fillRect(x,y,w,h);g.strokeStyle=color;g.lineWidth=4;g.strokeRect(x+2,y+2,w-4,h-4);stLabel(s,x+22,y+8,w-44,h-16,60,color);}
function stArrow(x,y,len,t,p=1){p=clamp(p);g.strokeStyle=C.orange;g.lineWidth=6;g.beginPath();g.moveTo(x,y);g.lineTo(x+len*p,y);if(p>.95){g.lineTo(x+len-17,y-13);g.moveTo(x+len,y);g.lineTo(x+len-17,y+13);}g.stroke();if(p>.9){g.fillStyle=C.orange;g.beginPath();g.arc(x+len*((t*.5)%1),y,5,0,TAU);g.fill();}}
function stAppear(u,index,n){return clamp((u*n-index)*2+1);}
const BORDER=SECS.map(sc=>new Sk(8000+sc.i).rrect(140,sc.y0+250,1640,490,28,{w:3}).penOn());
function stDiagram(v,t,u,sc){
 if(v.kind==='flow'){
  const n=v.labels.length,gap=64,w=(1480-gap*(n-1))/n;
  v.labels.forEach((s,i)=>{const a=stAppear(u,i,n);g.save();g.globalAlpha=a;stBox(s,220+i*(w+gap),390-12*(1-a),w,150,i===n-1?C.orange:C.ink,i===n-1?C.orangeL:C.white);if(i<n-1)stArrow(220+i*(w+gap)+w+8,465,gap-16,t,a);g.restore();});
 }else if(v.kind==='comparison'){
  v.groups.forEach((col,k)=>{g.save();g.globalAlpha=stAppear(u,k,2);const x=220+k*820;stBox(col.title,x,285,650,115,k?C.orange:C.ink,k?C.orangeL:C.white);(col.items||[]).forEach((s,j)=>{g.save();g.globalAlpha*=stAppear(u,j,(col.items||[]).length);stLabel(s,x+35,430+j*80,580,68,52);g.restore();});g.restore();});
 }else if(v.kind==='bars'){
  const max=Math.max(1,...v.values),n=v.values.length,step=1450/n,w=step*.56;
  g.strokeStyle=C.ink;g.lineWidth=3;g.beginPath();g.moveTo(240,650);g.lineTo(1710,650);g.stroke();
  v.values.forEach((a,i)=>{const x=260+i*step,p=stAppear(u,i,n),h=300*a/max;g.fillStyle=i===n-1?C.orange:C.ink;g.fillRect(x,650-h*p,w,h*p);stLabel(v.labels[i],x-10,690,step-20,65,48);if(p>.9)stLabel(String(a),x,650-h-65,step-20,55,50,C.orange);});
 }else if(v.kind==='matrix'){
  const rows=v.values.length,cols=v.values[0].length,w=Math.min(360,1200/cols),h=Math.min(160,360/rows),x0=960-cols*w/2,y0=470-rows*h/2;
  v.values.forEach((r,i)=>r.forEach((value,j)=>{g.save();g.globalAlpha=stAppear(u,i*cols+j,rows*cols);stBox(String(value),x0+j*w,y0+i*h,w-14,h-14,(i+j)%2?C.orange:C.ink,(i+j)%2?C.orangeL:C.white);g.restore();}));
 }else if(v.kind==='layers'){
  const n=v.labels.length,h=n<=4?100:65,step=n<=4?120:75;v.labels.forEach((s,i)=>{g.save();g.globalAlpha=stAppear(u,i,n);stBox(s,360+i*14,280+i*step,1160,h,i%2?C.orange:C.ink,i%2?C.orangeL:C.white);g.restore();});
 }else if(v.kind==='attention'){
  const labels=v.labels.slice(1),n=labels.length,weights=v.weights||labels.map(()=>1),max=Math.max(...weights,1);stBox(v.labels[0],220,405,390,150,C.orange,C.orangeL);
  labels.forEach((s,i)=>{g.save();const p=stAppear(u,i,n);g.globalAlpha=p;const step=Math.min(140,400/n),h=Math.min(100,step-15),y=280+i*step;g.strokeStyle=C.orange;g.lineWidth=3;g.beginPath();g.moveTo(610,480);g.lineTo(650,y+h/2);g.stroke();stArrow(650,y+h/2,130,t,p);stBox(s,820,y,480,h);g.fillStyle=C.orange;g.fillRect(1370,y+h*.15,270*weights[i]/max*p,h*.7);g.restore();});
 }else if(v.kind==='custom'){
  if(typeof window.drawKnowledgeScene!=='function')throw new Error('custom.js must define window.drawKnowledgeScene');
  window.drawKnowledgeScene({ctx:g,t,progress:u,scene:v,shot:sc.s,palette:C,label:stLabel,box:stBox,arrow:stArrow});
 }
 if(v.note)stLabel(v.note,240,770,1440,75,52,C.orange);
}
function drawStudio(t,viewBox){for(const sc of SECS){if(!seen(viewBox,sc.y0,sc.y0+1000)||t<sc.st-.1)continue;const {s,i,y0,st}=sc;const u=P(t,st+.4,Math.max(.4,s.end-st-.65));g.save();g.translate(0,y0);tag('@'+(i+1),190,100,44,P(t,st,.2));stLabel(s.title,390,52,1300,115,68);g.restore();BORDER[i].at(t,st+.18,.6);g.save();g.translate(0,y0);g.globalAlpha=P(t,st+.3,.3);stDiagram(sc.v,t,u,sc);g.restore();}}
