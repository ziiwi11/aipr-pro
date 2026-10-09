const test = require('node:test');
const assert = require('node:assert/strict');
const { collectDeliveredContacts } = require('./delivery-exclusions.cjs');
const { mergeRuntimeCollectionStrategy } = require('./collection-strategy-runtime.cjs');
test('new brand excludes delivered channels across saved delivery formats', () => {
  const contacts = collectDeliveredContacts([
    { rows: [{ 微信: 'same_wechat', 手机号: '138****0000' }] },
    { candidates: [{ buyin_contact_wechat: 'same_wechat', cart_contact_phone: '13800000001' }] },
  ]);
  assert.deepEqual(contacts, ['same_wechat', '13800000001']);
  const strategy = mergeRuntimeCollectionStrategy({ base: {}, deliveredContacts: contacts });
  assert.deepEqual(strategy.excludeContacts, contacts);
});

const {filterImportedCopies}=require('./delivery-exclusions.cjs');
test('an imported copy cannot evict creators from its source task',()=>{
 const own={rows:[{主页身份ID:'one',微信:'wx_one',手机号:'13800000001'}]};
 const copy={rows:[{主页身份ID:'one',微信:'wx_one',手机号:'13800000001'},{主页身份ID:'new',微信:'wx_new'}]};
 const result=filterImportedCopies(copy,[own]);
 assert.deepEqual(result.rows,[copy.rows[1]]);assert.equal(copy.rows.length,2);
});
test('same contact with another identity and changed channels remain exclusions',()=>{
 const own={rows:[{主页身份ID:'one',微信:'wx_one'}]};
 const other={rows:[{主页身份ID:'two',微信:'wx_one'},{主页身份ID:'one',微信:'wx_changed'},{微信:'wx_one'}]};
 assert.deepEqual(filterImportedCopies(other,[own]).rows,other.rows);
});
