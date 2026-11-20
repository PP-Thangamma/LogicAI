(() => {
 let last=""; let initialized=false;
 async function poll(){
  try{
   const r=await fetch(`/api/updates?since=${encodeURIComponent(last)}`);
   if(!r.ok)return;
   const d=await r.json();
   if(!initialized){last=d.server_time||"";initialized=true;return;}
   if(d.updates&&d.updates.length){
    window.dispatchEvent(new CustomEvent("logicai:updates",{detail:{count:d.updates.length}}));
    const notice=document.getElementById("live-update-notice");
    if(notice){notice.hidden=false;notice.textContent="New ticket activity is available. Refresh when you are ready.";}
   }
   if(d.server_time)last=d.server_time;
  }catch(e){}
 }
 setInterval(poll,12000);
})();
