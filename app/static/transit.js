const feedback=document.querySelector('#feedback');const meta=window.runMeta;async function perform(url,options){feedback.textContent='计算中…';try{const response=await fetch(url,options);const body=await response.json();if(!response.ok)throw Error(body.message||'请求失败');location.reload();}catch(error){feedback.textContent=error.message;}}document.querySelector('#rerun').addEventListener('click',()=>perform('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sample:document.querySelector('#sample').value})}));document.querySelector('#upload').addEventListener('click',()=>{const file=document.querySelector('#file').files[0];if(!file){feedback.textContent='请选择CSV文件。';return;}const data=new FormData();data.append('file',file);perform('/api/upload',{method:'POST',body:data});});document.querySelector('#review').addEventListener('click',()=>perform(`/api/runs/${meta.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:meta.version,decision:'已复核'})}));document.querySelector('#filter')?.addEventListener('input',event=>{for(const row of document.querySelectorAll('#records tr'))row.hidden=!row.textContent.toLowerCase().includes(event.target.value.toLowerCase());});
const sourceInput=document.querySelector('#source-name');
async function chunkPerform(url,options){
  const status=document.querySelector('#feedback');
  status.textContent='上传中…';
  try{const response=await fetch(url,options);const body=await response.json();
    if(!response.ok)throw Error(body.message||'请求失败');
    status.textContent=body.complete?`分块已收齐（${body.received_count}/${body.parts}），可结算。`:`已收 ${body.received_count}/${body.parts}，缺少 ${body.missing.join(',')}。`;
    if(body.complete)setTimeout(()=>location.reload(),400);return body;
  }catch(error){status.textContent=error.message;throw error;}
}
document.querySelector('#chunk-upload')?.addEventListener('click',async()=>{
  const source=(sourceInput?.value||'').trim();
  if(!source){feedback.textContent='请填写来源标识，同一来源重试不会新增批次。';return;}
  const files=[...(document.querySelector('#chunk-files')?.files||[])];
  if(!files.length){feedback.textContent='请选择按顺序排列的分块文件。';return;}
  const ordered=files.slice().sort((a,b)=>a.name.localeCompare(b.name,'zh-Hans-CN',{numeric:true}));
  for(let index=0;index<ordered.length;index++){
    const data=new FormData();data.append('file',ordered[index]);data.append('parts',String(ordered.length));
    await chunkPerform(`/api/sources/${encodeURIComponent(source)}/parts/${index+1}`,{method:'POST',body:data});
  }
});
document.querySelector('#chunk-finalize')?.addEventListener('click',async()=>{
  const source=(sourceInput?.value||'').trim();
  if(!source){feedback.textContent='请填写来源标识。';return;}
  feedback.textContent='结算中…';
  try{
    const response=await fetch(`/api/sources/${encodeURIComponent(source)}/finalize`,{method:'POST'});
    const body=await response.json();
    if(!response.ok)throw Error(body.message||'请求失败');
    feedback.textContent='已生成完整卡日结算批次，正在刷新。';
    setTimeout(()=>location.reload(),400);
  }catch(error){feedback.textContent=error.message;}
});
