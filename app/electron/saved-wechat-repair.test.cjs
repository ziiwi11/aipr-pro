const test=require('node:test'),assert=require('node:assert/strict');
const {savedWechatRepairs,reconcileContactReview}=require('./saved-wechat-repair.cjs');
test('repair uses labelled creator-specific original evidence, preserving other channels',()=>{
 const raw=[{identity:'u',ui_contact_items_after:['达人手机号：13800000000','达人微信号：A13800000000']}];
 const rows=[{id:'u',wechat:'13800000000',phone:'13900000000',email:''}];
 const fixes=savedWechatRepairs(raw,rows);
 assert.equal(fixes.length,1);assert.equal(fixes[0].wechat,'A13800000000');assert.equal(fixes[0].phone,'13900000000');assert.equal(rows[0].wechat,'13800000000');
});
test('never override manual revisions, masked values, unrelated evidence, or ambiguous labels',()=>{
 const raw=[{identity:'u',ui_contact_items_after:['达人微信号：********','达人手机号：A13800000000']}];
 assert.equal(savedWechatRepairs(raw,[{id:'u',wechat:'13800000000'}]).length,0);
 const valid=[{identity:'u',ui_contact_items_after:['达人微信号：A13800000000']}];
 assert.equal(savedWechatRepairs(valid,[{id:'u',wechat:'13800000000',contactCorrectionRevision:1}]).length,0);
 assert.equal(savedWechatRepairs(valid,[{id:'other',wechat:'13800000000'}]).length,0);
});

test('after repair compare current values without rewriting original review evidence',()=>{
 const report={records:[{identity:'u',contact_verification:{channels:{wechat:'platform_mismatch'},observed_channels:{wechat:'A13800000000'},reachability:'unverified'}}]};
 const next=reconcileContactReview(report,[{id:'u',wechat:'A13800000000',contactCorrectionRevision:1}]);
 assert.equal(next.records[0].contact_verification.channels.wechat,'platform_match');
 assert.equal(report.records[0].contact_verification.channels.wechat,'platform_mismatch');
 assert.equal(next.records[0].contact_verification.reachability,'unverified');
});
