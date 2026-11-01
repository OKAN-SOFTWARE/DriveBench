"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const node = (tag, cls, value) => { const result=document.createElement(tag); if(cls)result.className=cls; if(value!==undefined)result.textContent=value; return result; };
  let catalog, vehicles=[], selectedVehicle=null, mode="manual", readingIndex=0, saving=false, reportRequest=0;
  async function request(path, options) { const response=await fetch(path,options); const data=await response.json(); if(!response.ok)throw new Error(data.error || `HTTP ${response.status}`); return data; }
  const post = (path,body) => request(path,{method:"POST",headers:{"Content-Type":"application/json","X-DriveBench":"1"},body:JSON.stringify(body)});
  function message(text, success=false) { byId("garage-message").hidden=!text; byId("garage-message").textContent=text; byId("garage-message").className=success?"garage-success":"error"; }
  function option(value,label) { const result=node("option","",label); result.value=value; return result; }
  function label(text,input) { const result=node("label","",text); result.append(input); return result; }
  function numeric(id) { const value=byId(id).value; return value===""?null:Number(value); }
  function workspace(name) { ["garage","lab"].forEach(id=>{ byId(id+"-panel").hidden=id!==name; byId(id+"-nav").setAttribute("aria-pressed",String(id===name)); }); }
  byId("garage-nav").addEventListener("click",()=>workspace("garage"));
  byId("lab-nav").addEventListener("click",()=>workspace("lab"));

  function referencePanel(vehicle) {
    const container=byId("vehicle-reference"); container.replaceChildren();
    const profile=catalog.profiles.find(p=>p.id===vehicle.profile_id);
    if(!profile) { const card=node("div","reference-card unavailable"); card.append(node("span","outline-tag","REFERENCE UNAVAILABLE"),node("h3","","Record readings without guessing limits."),node("p","muted","This custom vehicle has no reviewed reference in the bundled catalog. Battery, coolant, RPM, and speed readings can be saved, but will not receive a normal/fault classification.")); container.append(card); return; }
    const reference=catalog.references[profile.reference_id], card=node("div","reference-card");
    card.append(node("span","outline-tag","REVIEWED OWNER-MANUAL REFERENCE"),node("h3","",reference.title));
    const bands=node("div","reference-bands"); reference.bands.forEach(band=>{const item=node("div");item.append(node("strong","",`${band.min}–${band.max} V`),node("span","",band.label.replace(" reference band","")));bands.append(item);});
    card.append(bands,node("p","muted",reference.conditions),node("p","muted",reference.scope));
    const source=node("a","source-link",`${profile.source.title} · p. ${profile.source.page} ↗`); source.href=profile.source.url;source.target="_blank";source.rel="noopener noreferrer";
    card.append(source,node("p","reference-coverage","Coverage: resting battery voltage only. Coolant temperature, charging voltage, RPM, and speed have no bundled limits."));container.append(card);
  }
  function profilePreview() {
    const selected=byId("profile-choice").value, profile=catalog.profiles.find(p=>p.id===selected);
    byId("custom-vehicle-fields").hidden=Boolean(profile);
    byId("custom-vehicle-fields").querySelectorAll("input,select").forEach(input=>{input.disabled=Boolean(profile);input.required=!profile;});
    byId("profile-preview").textContent=profile?`${profile.engine} · ${profile.market} · resting-battery reference only`:"Custom vehicles have no bundled reference ranges.";
  }
  function renderVehicles() {
    byId("vehicle-count").textContent=vehicles.length;
    const list=byId("vehicles");list.replaceChildren();
    if(!vehicles.length)list.append(node("p","muted","No vehicles yet. Add your first below."));
    vehicles.forEach(vehicle=>{const button=node("button","vehicle-choice"+(selectedVehicle===vehicle.id?" selected":""));button.type="button";button.setAttribute("aria-pressed",String(selectedVehicle===vehicle.id));button.append(node("span","vehicle-choice-name",vehicle.nickname),node("span","vehicle-choice-model",`${vehicle.year} ${vehicle.make} ${vehicle.model}`),node("span","vehicle-choice-ref",vehicle.profile_id?"1 sourced reference":"Reference unavailable"));button.addEventListener("click",()=>selectVehicle(vehicle.id));list.append(button);});
  }
  async function selectVehicle(identifier) {
    selectedVehicle=identifier; reportRequest++; byId("assessment-result").hidden=true; renderVehicles();
    const vehicle=vehicles.find(v=>v.id===identifier);byId("vehicle-empty").hidden=Boolean(vehicle);byId("vehicle-workspace").hidden=!vehicle;
    if(!vehicle)return;
    byId("vehicle-eyebrow").textContent=`MY GARAGE / ${vehicle.nickname.toUpperCase()}`;
    byId("vehicle-name").textContent=`${vehicle.year} ${vehicle.make} ${vehicle.model}`;
    byId("vehicle-config").textContent=`${vehicle.engine} · ${vehicle.powertrain} · ${vehicle.market}`;
    referencePanel(vehicle); await refreshHistory();
  }
  byId("profile-choice").addEventListener("change",profilePreview);
  byId("vehicle-form").addEventListener("submit",async event=>{
    event.preventDefault();const button=event.target.querySelector("button[type=submit]");if(button.disabled)return;button.disabled=true;message("");
    const data=new FormData(event.target), body=Object.fromEntries(data);if(!body.profile_id)body.year=Number(body.year);
    try { const vehicle=await post("/api/vehicles",body);vehicles=await request("/api/vehicles");await selectVehicle(vehicle.id);byId("add-vehicle").open=false;event.target.reset();profilePreview();message("Vehicle saved to your local garage.",true); }
    catch(error){message(error.message);}finally{button.disabled=false;}
  });

  function addReading() {
    const container=byId("reading-rows");if(container.children.length>=50){message("Use CSV import for more than 50 manual readings.");return;}
    const row=node("div","reading-row"), index=++readingIndex;
    const signal=node("select");signal.className="reading-signal";signal.setAttribute("aria-label",`Signal ${index}`);
    Object.entries(catalog.signals).forEach(([id,definition])=>signal.append(option(id,definition.name)));
    const value=node("input");value.type="number";value.step="any";value.className="reading-value";value.placeholder="Blank = missing";value.setAttribute("aria-label",`Value ${index}`);
    const unit=node("select");unit.className="reading-unit";unit.setAttribute("aria-label",`Unit ${index}`);
    const at=node("input");at.type="datetime-local";at.step="1";at.required=true;at.className="reading-at";at.setAttribute("aria-label",`Local timestamp ${index}`);
    const now=new Date();at.value=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,19);
    const remove=node("button","remove-reading","×");remove.type="button";remove.setAttribute("aria-label",`Remove reading ${index}`);remove.addEventListener("click",()=>{if(container.children.length>1)row.remove();else message("Keep one reading, or switch to CSV import.");});
    const updateUnits=()=>{unit.replaceChildren();catalog.signals[signal.value].units.forEach(u=>unit.append(option(u,u)));};signal.addEventListener("change",updateUnits);updateUnits();
    row.append(label("Signal",signal),label("Value",value),label("Unit",unit),label("Local timestamp",at),remove);container.append(row);
  }
  byId("add-reading").addEventListener("click",addReading);
  function setMode(next) {
    mode=next;byId("manual-input").hidden=next!=="manual";byId("csv-input").hidden=next!=="csv";
    ["manual","csv"].forEach(id=>byId(id+"-mode").setAttribute("aria-pressed",String(id===next)));
    byId("manual-input").querySelectorAll("input,select,button").forEach(input=>input.disabled=next!=="manual");
    byId("csv-input").querySelectorAll("input,textarea").forEach(input=>input.disabled=next!=="csv");
  }
  byId("manual-mode").addEventListener("click",()=>setMode("manual"));byId("csv-mode").addEventListener("click",()=>setMode("csv"));
  byId("csv-file").addEventListener("change",async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>512*1024)throw new Error("CSV must be at most 512 KiB.");byId("csv-text").value=await file.text();message(`${file.name} loaded. Review it, then compare readings.`,true);}catch(error){message(error.message);}});
  byId("assessment-form").addEventListener("submit",async event=>{
    event.preventDefault();if(saving||!selectedVehicle)return;saving=true;byId("compare-readings").disabled=true;message("");
    const vehicleId=selectedVehicle,body={vehicle_id:vehicleId,name:byId("assessment-name").value};
    try {
      if(mode==="csv")body.csv=byId("csv-text").value;
      else body.readings=Array.from(byId("reading-rows").children).map(row=>({at:new Date(row.querySelector(".reading-at").value).toISOString(),signal:row.querySelector(".reading-signal").value,value:row.querySelector(".reading-value").value===""?null:Number(row.querySelector(".reading-value").value),unit:row.querySelector(".reading-unit").value,condition:byId("reading-condition").value,ambient_c:numeric("reading-ambient"),rest_minutes:numeric("reading-rest"),lights_off:byId("reading-lights").value===""?null:byId("reading-lights").value==="true",measurement_source:byId("reading-source").value}));
      const report=await post("/api/assessments",body);
      if(vehicleId===selectedVehicle){reportRequest++;renderReport(report);await refreshHistory();message("Session saved. Expand each result to inspect its reference and conditions.",true);byId("assessment-result").scrollIntoView({behavior:"smooth",block:"start"});}
    }catch(error){message(error.message);}finally{saving=false;byId("compare-readings").disabled=false;}
  });

  async function refreshHistory() {
    const vehicleId=selectedVehicle,history=await request("/api/assessments");if(vehicleId!==selectedVehicle)return;
    const container=byId("assessment-history");container.replaceChildren();const visible=history.filter(r=>r.vehicle.id===vehicleId);
    if(!visible.length)container.append(node("p","muted","No sessions for this vehicle yet."));
    visible.forEach(report=>{const button=node("button","assessment-history-item");button.type="button";button.append(node("strong","",report.name),node("span","",`${new Date(report.created_at).toLocaleString()} · ${report.summary.readings} readings · ${report.summary.flagged} flagged`));button.addEventListener("click",async()=>{const serial=++reportRequest;try{const full=await request(`/api/assessments/${report.id}`);if(serial===reportRequest&&selectedVehicle===report.vehicle.id){renderReport(full);byId("assessment-result").scrollIntoView({behavior:"smooth",block:"start"});}}catch(error){message(error.message);}});container.append(button);});
  }
  function renderReport(report) {
    byId("assessment-result").hidden=false;byId("assessment-id").textContent=`SESSION / ${report.id.slice(0,12)} · CATALOG ${report.catalog_version}`;
    byId("assessment-title").textContent=report.name;byId("assessment-meta").textContent=`${report.vehicle.year} ${report.vehicle.make} ${report.vehicle.model} · ${new Date(report.created_at).toLocaleString()} · ${report.origin.toUpperCase()}`;
    byId("assessment-json").href=`/api/assessments/${report.id}/export.json`;byId("assessment-text").href=`/api/assessments/${report.id}/report.txt`;
    const summary=byId("assessment-summary");summary.replaceChildren();
    [[report.summary.readings,"READINGS"],[report.summary.compared,"COMPARED WITH REFERENCE"],[report.summary.flagged,"FLAGGED FOR REVIEW"],[report.summary.unavailable,"REFERENCE UNAVAILABLE"],[report.summary.conditions_not_met,"CONDITIONS NOT MET"],[report.summary.missing,"MISSING"]].forEach(([value,title])=>{const item=node("div");item.append(node("strong","",value),node("span","",title));summary.append(item);});
    const container=byId("measurement-results");container.replaceChildren();
    report.readings.forEach((reading,index)=>{
      const details=node("details","measurement-result"+(reading.flagged?" flagged":"")),heading=node("summary");
      const signal=node("div","result-signal");signal.append(node("strong","",catalog.signals[reading.signal].name),node("span","",new Date(reading.at).toLocaleString()));
      heading.append(node("span","reading-number",String(index+1).padStart(2,"0")),signal,node("strong","measurement-value",reading.value===null?"MISSING":`${Number(reading.value.toFixed(3))} ${reading.unit}`),node("span",`measurement-label ${reading.status}`,reading.label));
      const explanation=node("div","reading-explanation");explanation.append(node("p","",reading.explanation),node("p","muted",`Exact normalized value: ${reading.value === null ? "missing" : reading.value} ${reading.unit}.`));
      explanation.append(node("p","muted",`Recorded conditions: ${reading.condition} · ${reading.ambient_c===null?"ambient unknown":reading.ambient_c+" °C"} · ${reading.rest_minutes===null?"rest unknown":reading.rest_minutes+" minutes after switch-off"} · lights off: ${reading.lights_off===null?"unknown":reading.lights_off?"yes":"no"} · ${reading.measurement_source}`));
      if(reading.original_unit!==reading.unit)explanation.append(node("p","muted",`Converted from ${reading.original_value} ${reading.original_unit}.`));
      if(reading.unmet_conditions.length){explanation.append(node("h4","","Missing or unmatched conditions"));const list=node("ul");reading.unmet_conditions.forEach(item=>list.append(node("li","",item)));explanation.append(list);}
      if(reading.reference)explanation.append(node("p","muted",reading.reference.conditions),node("p","muted",reading.reference.scope));
      if(reading.source){const source=node("a","source-link",`${reading.source.publisher} · ${reading.source.document} · page ${reading.source.page} ↗`);source.href=reading.source.url;source.target="_blank";source.rel="noopener noreferrer";explanation.append(source,node("p","reference-coverage",`Reviewed ${reading.source.reviewed_at} · applicability: ${report.vehicle.market}, ${report.vehicle.year} ${report.vehicle.model}, ${report.vehicle.engine}`));}
      details.append(heading,explanation);container.append(details);
    });
  }
  async function init() {
    try { [catalog,vehicles]=await Promise.all([request("/api/catalog"),request("/api/vehicles")]);catalog.profiles.forEach(profile=>byId("profile-choice").append(option(profile.id,`${profile.year} ${profile.make} ${profile.model} · ${profile.market}`)));profilePreview();addReading();setMode("manual");renderVehicles();if(vehicles.length){byId("add-vehicle").open=false;await selectVehicle(vehicles[0].id);} }
    catch(error){message(`Cannot load My Garage: ${error.message}`);}
  }
  init();
})();
