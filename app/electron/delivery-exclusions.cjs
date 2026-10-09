function collectDeliveredIdentities(deliveries = []) {
  const identities = new Set();
  for (const delivery of deliveries) {
    for (const row of delivery?.rows || delivery?.candidates || []) {
      for (const value of [
        row?.["主页身份ID"], row?.["抖音号"], row?.identity, row?.buyin_uid,
        row?.douyin_id, row?.author_id, row?.sec_uid,
      ]) {
        const clean = String(value || "").trim();
        if (clean) identities.add(clean);
      }
    }
  }
  return [...identities];
}

module.exports = { collectDeliveredIdentities };

function collectDeliveredContacts(deliveries = []) {
  const contacts = new Set();
  for (const delivery of deliveries) for (const row of delivery?.rows || delivery?.candidates || []) {
    for (const key of ['微信', '手机号', '邮箱', 'wechat', 'phone', 'email',
      'buyin_contact_wechat', 'cart_contact_wechat', 'buyin_contact_phone',
      'cart_contact_phone', 'buyin_contact_email', 'cart_contact_email']) {
      const value = String(row?.[key] || '').trim();
      if (value && !/[*•]|隐藏|未授权|待获取|待补|暂无|不可见/u.test(value)) contacts.add(value);
    }
  }
  return [...contacts];
}
module.exports.collectDeliveredContacts = collectDeliveredContacts;

function taskLineage(task={}) {
 const match=String(task.outputDir||'').match(/\/恢复-\d+\/brand-tasks\/([^/]+)\/?$/);
 return String(task.id||'').includes('-restored')&&match ? match[1] : String(task.id||'');
}
function deliveryExclusionTasks(tasks=[],currentId='') {
 const current=tasks.find(task=>task.id===currentId)||{id:currentId};
 const own=taskLineage(current),groups=new Map();
 for(const task of tasks){const lineage=taskLineage(task);if(lineage===own)continue;const previous=groups.get(lineage);if(!previous||task.id===lineage)groups.set(lineage,task);}
 return [...groups.values()];
}
module.exports.taskLineage=taskLineage;
module.exports.deliveryExclusionTasks=deliveryExclusionTasks;

// Imported snapshots are references to existing data, not a new collection.
// Ignore exact copies already owned by the task being resumed. A different
// identity or changed contact remains a genuine cross-task exclusion.
function filterImportedCopies(delivery = {}, ownDeliveries = []) {
 const ownRows=ownDeliveries.flatMap(item=>item?.rows||item?.candidates||[]);
 const exactCopy=row=>{
  const ids=new Set(collectDeliveredIdentities([{rows:[row]}]));
  const contacts=collectDeliveredContacts([{rows:[row]}]).map(v=>v.toLowerCase()).sort();
  if(!ids.size||!contacts.length)return false;
  return ownRows.some(own=>{
   if(!collectDeliveredIdentities([{rows:[own]}]).some(id=>ids.has(id)))return false;
   const other=collectDeliveredContacts([{rows:[own]}]).map(v=>v.toLowerCase()).sort();
   return JSON.stringify(contacts)===JSON.stringify(other);
  });
 };
 const key=Array.isArray(delivery.rows)?'rows':'candidates';
 return {...delivery,[key]:(delivery[key]||[]).filter(row=>!exactCopy(row))};
}
module.exports.filterImportedCopies=filterImportedCopies;
