import type {CollectionStrategy} from "./types";
export const CREATOR_TYPES = ["不限内容类型", "美妆护肤", "测评种草", "生活好物", "穿搭分享", "母婴育儿", "食品分享"];
export const PRESENTATIONS = [{value:"any",label:"不限出镜方式"},{value:"real_person",label:"真人出镜（需作品证据）"},{value:"hands_only",label:"手部展示（需作品证据）"},{value:"product_only",label:"纯产品展示（需作品证据）"}];
export const CATEGORIES = ["美妆个护", "玩具乐器", "服饰内衣", "个护家清", "智能家居", "生鲜", "美妆", "母婴宠物", "鲜花园艺", "本地生活", "食品饮料", "3C数码家电", "图书教育", "鞋靴箱包", "虚拟充值", "运动户外", "钟表配饰", "珠宝文玩", "医疗健康", "酒类", "滋补保健", "原料包装", "餐饮外卖"];
/** Copy explicit source fields only. Unlabelled prose stays in the brief for review. */
export function parseBrief(text:string): {fields:Partial<CollectionStrategy>;sources:Record<string,string>;unresolved:string[]} {
 const fields:Partial<CollectionStrategy>={brief:text};const sources:Record<string,string>={};
 const names:Record<string,string>={品牌:"brandName",品牌名称:"brandName",产品:"productName",产品名称:"productName",商品名称:"productName",核心卖点:"sellingPoints",卖点:"sellingPoints",适配条件:"criteria",达人要求:"criteria",排除条件:"exclusions",排除:"exclusions",类目:"category",目标类目:"category",达人类型:"creatorType",出镜方式:"contentPresentation"};
 const unresolved:string[]=[];
 for(const line of text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)){
  const match=line.match(/^([^:：]{1,12})[:：]\s*(.+)$/);if(!match||!names[match[1]]){unresolved.push(line);continue;}
  const key=names[match[1]],value=match[2].trim();
  if(key==="category"&&!CATEGORIES.includes(value)){unresolved.push(line);continue;}
  if(key==="creatorType"&&!CREATOR_TYPES.includes(value)){unresolved.push(line);continue;}
  if(key==="contentPresentation"){
   const choice=PRESENTATIONS.find(x=>x.value===value||x.label.replace("（需作品证据）","")===value);
   if(!choice){unresolved.push(line);continue;} fields[key]=choice.value;
  }else if(key==="exclusions") fields.exclusions=value.split(/[、,，;；]/).map(x=>x.trim()).filter(Boolean);
  else fields[key]=value;
  sources[key]=line;
 }
 return {fields,sources,unresolved};
}
