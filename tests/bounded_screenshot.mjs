import fs from 'node:fs';
import path from 'node:path';

// Screenshot transport only: never alter the application, device scale or data.
export function planCapture(height,viewportHeight,dpr,width,pixelLimit=30000){
  if(![height,viewportHeight,dpr,width,pixelLimit].every(v=>Number.isFinite(v)&&v>0))throw Error('Invalid screenshot dimensions');
  if(width*dpr>pixelLimit||viewportHeight*dpr>pixelLimit)throw Error('Viewport exceeds screenshot transport bound');
  if(height*dpr<=pixelLimit)return {mode:'full',offsets:[0]};
  const last=Math.max(0,Math.ceil(height-viewportHeight)),step=Math.max(1,Math.floor(viewportHeight-Math.min(160,viewportHeight/3))),offsets=[];
  for(let y=0;y<last;y+=step){if(offsets.length>=199)throw Error('Page exceeds bounded capture budget; no truncated acceptance');offsets.push(y);}
  offsets.push(last);return {mode:'viewport-sections',offsets};
}
export async function capturePage(page,filename){
  const dims=await page.evaluate(()=>({height:Math.max(document.documentElement.scrollHeight,document.body?.scrollHeight||0),viewportHeight:innerHeight,width:innerWidth,dpr:devicePixelRatio||1,x:scrollX,y:scrollY}));
  const plan=planCapture(dims.height,dims.viewportHeight,dims.dpr,dims.width);
  if(plan.mode==='full'){await page.screenshot({path:filename,fullPage:true});return {mode:'full',files:[path.basename(filename)],height:dims.height};}
  const ext=path.extname(filename),stem=filename.slice(0,-ext.length),sections=[];
  try{
    for(const [index,y] of plan.offsets.entries()){
      const position=await page.evaluate(async top=>{
        window.scrollTo(0,top);
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        return {y:scrollY,height:Math.max(document.documentElement.scrollHeight,document.body?.scrollHeight||0)};
      },y);
      if(position.height!==dims.height)throw Error('Page height changed during capture; do not silently truncate');
      const file=`${stem}-part-${String(index+1).padStart(3,'0')}${ext}`;
      await page.screenshot({path:file,fullPage:false});
      sections.push({file:path.basename(file),top:position.y,bottom:Math.min(dims.height,position.y+dims.viewportHeight)});
    }
    if(sections[0].top>2||sections.at(-1).bottom<dims.height-2||sections.some((s,i)=>i&&s.top>sections[i-1].bottom))throw Error('Screenshot coverage has a gap');
    const report={mode:plan.mode,height:dims.height,viewportHeight:dims.viewportHeight,devicePixelRatio:dims.dpr,fullVerticalCoverage:true,sections};
    fs.writeFileSync(stem+'-capture.json',JSON.stringify(report,null,2)+'\n');return report;
  }finally{await page.evaluate(({x,y})=>window.scrollTo(x,y),dims);}
}
export async function verifyCaptureLimit(browser,options,label,out,check){
  const context=await browser.newContext(options),page=await context.newPage();
  try{
    // Isolated long test document exceeds the iPhone screenshot limit without
    // changing any live page or dismissing content to make the test pass.
    const height=14000;
    await page.setContent(`<main style="height:${height}px"><h1>TEST ONLY: complete long-page capture</h1><p style="position:absolute;top:${height-80}px">TEST END MARKER</p></main>`);
    const report=await capturePage(page,path.join(out,label+'-long-capture-fixture.png'));
    check(`${label}: long screenshot keeps device scale and complete vertical coverage`,(options.deviceScaleFactor||1)*height>30000 ? report.mode==='viewport-sections'&&report.fullVerticalCoverage===true&&report.sections.length>1 : report.mode==='full');
    check(`${label}: long screenshot restores original scroll`,await page.evaluate(()=>scrollY)===0);
  }finally{await context.close();}
}
