const test = require("node:test");
const assert = require("node:assert/strict");
const { setShopViewLayout } = require("./shop-view-layout.cjs");
test("hidden shop retains a nonzero viewport and stays invisible for background evidence", () => {
 const events = []; const view = {setBounds: b => events.push(["bounds", b]), setVisible: v => events.push(["visible", v])};
 setShopViewLayout(view, false);
 assert.equal(events[0][0], "bounds");
 assert.ok(events[0][1].width >= 1000 && events[0][1].height >= 700);
 assert.deepEqual(events[1], ["visible", false]);
});
test("switching shops and hiding preserves capture dimensions without overlaying the app", () => {
 const view = {setBounds(b) {this.bounds=b}, setVisible(v) {this.visible=v}};
 const bounds = {x:10,y:20,width:1100,height:800};
 setShopViewLayout(view,true,bounds); assert.deepEqual(view.bounds,bounds); assert.equal(view.visible,true);
 setShopViewLayout(view,false);assert.ok(view.bounds.width>0 && view.bounds.height>0);assert.equal(view.visible,false);
 setShopViewLayout(undefined,false);
});
